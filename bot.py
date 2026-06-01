#!/usr/bin/env python3
"""
LinkedIn DevOps Bot — GitHub Actions edition
=============================================
Each cron trigger runs this script ONCE and posts ONE post.
5 cron triggers per day  →  5 posts per day.

No scheduler library needed. No long-running process.
Just: generate → post → exit.

Env vars (set as GitHub Secrets):
  ANTHROPIC_API_KEY       Your Anthropic API key
  LINKEDIN_ACCESS_TOKEN   OAuth 2.0 token (w_member_social scope)
  LINKEDIN_PERSON_URN     urn:li:person:XXXXXXX
  DRY_RUN                 "true" to print without posting (default: false)
  POST_TOPIC              Force a specific topic (optional, default: auto-rotate)
"""

import os
import sys
import random
import hashlib
import logging
import requests
import anthropic
from datetime import datetime, timezone

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

ANTHROPIC_API_KEY     = os.environ["ANTHROPIC_API_KEY"]
LINKEDIN_ACCESS_TOKEN = os.environ.get("LINKEDIN_ACCESS_TOKEN", "")
LINKEDIN_PERSON_URN   = os.environ.get("LINKEDIN_PERSON_URN", "")
DRY_RUN               = os.environ.get("DRY_RUN", "false").lower() == "true"
FORCE_TOPIC           = os.environ.get("POST_TOPIC", "auto").lower()

CLAUDE_MODEL   = "claude-sonnet-4-20250514"
LINKEDIN_URL   = "https://api.linkedin.com/v2/ugcPosts"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# TOPIC ROTATION
# Auto-selects a different topic for each of the
# 5 daily posts using UTC hour as a deterministic
# seed so reruns stay consistent.
# ─────────────────────────────────────────────

TOPICS = ["cicd", "kubernetes", "project", "debug", "charts_code"]

# Maps UTC hour → topic index (matches the 5 cron times in the workflow)
HOUR_TO_TOPIC = {
    2:  0,   # 2:30 AM UTC  → CI/CD
    5:  1,   # 5:00 AM UTC  → Kubernetes
    7:  2,   # 7:30 AM UTC  → Projects
    10: 3,   # 10:00 AM UTC → Debug tips
    12: 4,   # 12:30 PM UTC → Charts/code
}

def pick_topic() -> str:
    if FORCE_TOPIC and FORCE_TOPIC not in ("auto", "random", ""):
        if FORCE_TOPIC in TOPICS:
            return FORCE_TOPIC
        log.warning(f"Unknown topic '{FORCE_TOPIC}', falling back to auto-rotate.")

    hour = datetime.now(timezone.utc).hour
    idx  = HOUR_TO_TOPIC.get(hour, random.randint(0, len(TOPICS) - 1))
    return TOPICS[idx]

# ─────────────────────────────────────────────
# PROMPT LIBRARY
# 4 prompt variants per topic — random pick each
# run keeps content fresh across the week.
# ─────────────────────────────────────────────

PROMPTS = {
    "cicd": [
        """Write a LinkedIn post about a common CI/CD pipeline mistake that silently breaks production deployments.
Structure:
- Powerful hook (1 sentence)
- The mistake and why it happens (2-3 sentences)
- 4 bullet-point fixes with GitHub Actions YAML snippet where relevant
- Closing question to spark comments
Tone: senior engineer sharing hard-won experience. Max 280 words.
Hashtags: #DevOps #CICD #GitHubActions #Automation""",

        """Write a LinkedIn post: "How I cut our CI pipeline time from 18 minutes to 4 minutes."
Structure:
- Hook with the before/after numbers
- 5 concrete techniques (layer caching, parallelism, test splitting, artifact reuse, selective triggers)
- One real GitHub Actions YAML snippet (8-10 lines max)
- CTA asking readers to share their own tips
Tone: practical, not preachy. Max 280 words.
Hashtags: #DevOps #CICD #Docker #Performance""",

        """Write a LinkedIn post: "5 CI/CD metrics every DevOps engineer should track."
Cover: Deployment Frequency, Lead Time for Changes, MTTR, Change Failure Rate, Availability.
For each: one sentence on what it measures + one sentence on a healthy benchmark.
Close with a poll-style question.
Tone: educational but conversational. Max 280 words.
Hashtags: #DevOps #SRE #DORA #Metrics""",

        """Write a LinkedIn post about GitOps vs traditional push-based CI/CD pipelines.
Include: what each approach is (1-2 lines each), 3 pros of GitOps, 1 real gotcha, and when to stick with push-based.
Tone: balanced, experienced. Max 280 words.
Hashtags: #GitOps #DevOps #CICD #ArgoCD""",
    ],

    "kubernetes": [
        """Write a LinkedIn post: "Kubernetes CrashLoopBackOff — a 5-step debug checklist."
For each step include the exact kubectl command.
Steps: logs, describe, events, exec into container, resource limits check.
Open with a relatable frustration hook.
Tone: engineer-to-engineer, no fluff. Max 280 words.
Hashtags: #Kubernetes #DevOps #Debugging #K8s""",

        """Write a LinkedIn post explaining Kubernetes resource requests vs limits using a coffee-shop analogy, then back it up with a YAML example (6-8 lines).
Explain what happens when a pod exceeds its memory limit.
CTA: ask readers what their biggest K8s resource mistake was.
Tone: fun but technically accurate. Max 280 words.
Hashtags: #Kubernetes #K8s #DevOps""",

        """Write a LinkedIn post: "Kubernetes interview questions I actually ask — and the answers that impress me."
Include 4 questions ranging from beginner to advanced (pods vs deployments, HPA, etcd role, network policies).
Format each as: Question | Average answer | Great answer.
Tone: hiring-manager perspective, helpful. Max 280 words.
Hashtags: #Kubernetes #DevOps #Interviews #CloudNative""",

        """Write a LinkedIn post about liveness vs readiness vs startup probes — the difference most people get wrong.
Use a real-world analogy, show a minimal YAML snippet for each probe type.
Explain the exact consequence of misconfiguring each one.
Max 280 words.
Hashtags: #Kubernetes #K8s #DevOps #CloudNative""",
    ],

    "project": [
        """Write a LinkedIn post describing a weekend DevOps mini-project: a self-healing Kubernetes deployment using a liveness probe + Slack webhook alert when a pod restarts.
Format:
- "This weekend I built X" hook
- 5 numbered steps to build it
- What you will learn from it
Tone: encouraging, builder mindset. Max 280 words.
Hashtags: #DevOps #Kubernetes #LearningByDoing #SideProject""",

        """Write a LinkedIn post about a beginner DevOps project: monitoring server health with a Bash script that sends a Slack alert when CPU or disk hits a threshold.
Include a 10-line Bash snippet showing the core logic.
Explain how to schedule it with cron.
End with 3 ways to extend the project.
Tone: beginner-friendly. Max 280 words.
Hashtags: #DevOps #Linux #Bash #Monitoring""",

        """Write a LinkedIn post: "Build a complete CI/CD pipeline in one evening — the exact stack I would use."
Stack: GitHub Actions → Docker → ECR → EKS (or Render as a free alternative).
Give a 6-step walkthrough. Include one GitHub Actions trigger snippet.
End with: "What would you add to this stack?"
Max 280 words.
Hashtags: #DevOps #CICD #Docker #AWS #LearningByDoing""",

        """Write a LinkedIn post about a DevOps project: your staging environment keeps drifting from production.
Walk through building a drift-detection script using Terraform plan + Slack notification.
5 concrete steps with one Terraform or shell command per step.
Frame it as a real problem you solved. Max 280 words.
Hashtags: #DevOps #Terraform #IaC #SRE""",
    ],

    "debug": [
        """Write a LinkedIn post: "My daily kubectl cheat sheet — 8 commands I use every day."
For each: the command as code + one sentence on what it does.
Cover: logs with timestamps, wide output, exec into pod, port-forward, top nodes/pods, describe, rollout history.
Tone: quick reference, no padding. Max 280 words.
Hashtags: #Kubernetes #DevOps #kubectl #CloudNative""",

        """Write a LinkedIn post: story format — debugging a mysterious memory leak in a containerised Node.js app at 2am in production.
Structure: problem → clues → tools used (docker stats, heap dump, clinic.js) → root cause → fix.
Make it gripping but technical. Include 2 actual commands.
End with the lesson.
Max 280 words.
Hashtags: #DevOps #Docker #Debugging #NodeJS #SRE""",

        """Write a LinkedIn post: "Docker debugging commands that have saved me hours."
List 7 commands with a one-line explanation each:
docker logs, docker exec -it, docker inspect, docker stats, docker events, docker diff, docker system df.
Add one gotcha for 2 of them.
Tone: reference card style. Max 280 words.
Hashtags: #Docker #DevOps #Debugging #Containers""",

        """Write a LinkedIn post: debugging a Kubernetes pod stuck in Pending state.
Decision-tree style: check events → node resources → taints/tolerations → PVC → image pull.
Include kubectl commands for each step.
Frame it as "the checklist I wish I had on day 1."
Max 280 words.
Hashtags: #Kubernetes #DevOps #Debugging #K8s""",
    ],

    "charts_code": [
        """Write a LinkedIn post that is a DevOps lifecycle diagram using only text/emojis in the post itself.
Show all 8 stages (Plan, Code, Build, Test, Release, Deploy, Operate, Monitor) as a visual text diagram.
Give one real tool example per stage.
Tone: educational, visual. Max 280 words.
Hashtags: #DevOps #CICD #CloudNative #DevOpsTools""",

        """Write a LinkedIn post: "Linux commands every DevOps engineer must know — quick reference."
Format as a clean list of 10 commands with inline code and a 5-word description each.
Commands: awk, sed, grep -E, ss, lsof, strace, tcpdump, jq, xargs, watch.
Close with: "Which one took you longest to master?"
Max 280 words.
Hashtags: #Linux #DevOps #SRE #CommandLine""",

        """Write a LinkedIn post comparing Helm vs Kustomize for Kubernetes configuration management.
Use a simple text comparison table (3 rows: complexity, templating, use case).
Add your opinion on when to use each.
Be opinionated but fair. Max 280 words.
Hashtags: #Kubernetes #Helm #Kustomize #DevOps""",

        """Write a LinkedIn post: YAML vs JSON cheat sheet for DevOps engineers.
Show the same Kubernetes config snippet in both formats (8 lines each) side by side using a code block.
List 3 reasons YAML wins in K8s and 2 situations where JSON is better.
Max 280 words.
Hashtags: #DevOps #Kubernetes #YAML #JSON #CloudNative""",
    ],
}

# ─────────────────────────────────────────────
# GENERATE POST WITH CLAUDE
# ─────────────────────────────────────────────

SYSTEM_PROMPT = """You are a senior DevOps engineer with 10+ years of experience who writes
punchy, technically accurate LinkedIn posts that practitioners genuinely enjoy reading.

Rules:
- Never use filler openers like "In today's fast-paced world" or "As we navigate the digital landscape"
- Use real commands, real numbers, real analogies
- Format code and commands inside backticks
- Keep posts under 300 words total
- End with the hashtags provided in the prompt on a new line"""


def generate_post(topic: str) -> str:
    prompt_variants = PROMPTS[topic]

    # Deterministic seed so the same cron run always picks the same variant
    # (prevents duplicate posts if the job retries)
    day_seed = datetime.now(timezone.utc).strftime("%Y-%m-%d") + topic
    idx = int(hashlib.md5(day_seed.encode()).hexdigest(), 16) % len(prompt_variants)
    prompt = prompt_variants[idx]

    log.info(f"Calling Claude API for topic '{topic}' (variant {idx + 1}/{len(prompt_variants)})")

    client  = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    text = message.content[0].text.strip()
    log.info(f"Post generated: {len(text)} characters")
    return text

# ─────────────────────────────────────────────
# PUBLISH TO LINKEDIN
# ─────────────────────────────────────────────

def publish(text: str) -> bool:
    if DRY_RUN:
        print("\n" + "─" * 60)
        print("[DRY RUN] Post that would be published to LinkedIn:")
        print("─" * 60)
        print(text)
        print("─" * 60 + "\n")
        return True

    if not LINKEDIN_ACCESS_TOKEN:
        log.error("LINKEDIN_ACCESS_TOKEN is not set. Cannot publish.")
        return False
    if not LINKEDIN_PERSON_URN:
        log.error("LINKEDIN_PERSON_URN is not set. Cannot publish.")
        return False

    payload = {
        "author": LINKEDIN_PERSON_URN,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        },
    }

    headers = {
        "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }

    try:
        resp = requests.post(LINKEDIN_URL, headers=headers, json=payload, timeout=30)

        if resp.status_code in (200, 201):
            post_id = resp.headers.get("x-restli-id", "unknown")
            log.info(f"Published to LinkedIn successfully. Post ID: {post_id}")
            return True

        log.error(f"LinkedIn API error {resp.status_code}: {resp.text}")

        # Specific guidance for common errors
        if resp.status_code == 401:
            log.error("Token expired or invalid. Regenerate your LINKEDIN_ACCESS_TOKEN.")
        elif resp.status_code == 403:
            log.error("Missing permission. Ensure w_member_social scope is granted.")
        elif resp.status_code == 422:
            log.error("Invalid payload. Check LINKEDIN_PERSON_URN format: urn:li:person:XXXXX")

        return False

    except requests.Timeout:
        log.error("Request timed out. LinkedIn API may be slow — will retry on next cron.")
        return False
    except requests.RequestException as exc:
        log.error(f"Network error: {exc}")
        return False

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    log.info("=" * 60)
    log.info("LinkedIn DevOps Bot — starting")
    log.info(f"UTC time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}")
    log.info(f"Dry run: {DRY_RUN}")

    # 1. Pick topic
    topic = pick_topic()
    log.info(f"Selected topic: {topic}")

    # 2. Generate content
    try:
        post_text = generate_post(topic)
    except anthropic.AuthenticationError:
        log.error("Invalid ANTHROPIC_API_KEY. Check your GitHub secret.")
        sys.exit(1)
    except anthropic.RateLimitError:
        log.error("Claude API rate limit hit. The job will retry on the next cron trigger.")
        sys.exit(1)
    except Exception as exc:
        log.error(f"Unexpected error calling Claude API: {exc}")
        sys.exit(1)

    # 3. Publish
    success = publish(post_text)

    if success:
        log.info("Done.")
        sys.exit(0)
    else:
        log.error("Post failed. Check logs above.")
        sys.exit(1)   # Non-zero exit marks the GitHub Actions run as failed


if __name__ == "__main__":
    main()
