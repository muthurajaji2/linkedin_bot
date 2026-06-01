# LinkedIn DevOps Bot

Automatically generates and posts 5 DevOps posts per day to LinkedIn using
Claude AI, triggered by GitHub Actions cron jobs. Zero servers. Zero cost.

## Repo structure

```
.
├── .github/
│   └── workflows/
│       └── linkedin_bot.yml   ← GitHub Actions workflow (5 cron triggers/day)
├── bot.py                     ← The bot (generate + publish, runs once per trigger)
└── README.md
```

## Setup (10 minutes)

### 1. Fork or create this repo on GitHub

### 2. Add 3 GitHub Secrets

Go to **Settings → Secrets and variables → Actions → New repository secret**

| Secret name | Value |
|---|---|
| `ANTHROPIC_API_KEY` | Get from console.anthropic.com |
| `LINKEDIN_ACCESS_TOKEN` | Your OAuth 2.0 token (see below) |
| `LINKEDIN_PERSON_URN` | Your LinkedIn URN (see below) |

### 3. Get your LinkedIn credentials

**Access token:**
1. Go to https://www.linkedin.com/developers/apps → Create app
2. Add product: **"Share on LinkedIn"** → request `w_member_social` permission
3. Go to the **OAuth 2.0 tools** tab → generate a token with `w_member_social` scope
4. Token is valid for **60 days** — set a calendar reminder to refresh it

**Person URN:**
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" https://api.linkedin.com/v2/userinfo
```
The `sub` field is your person ID.  
Format it as: `urn:li:person:YOUR_ID`

### 4. Test with a dry run

Go to **Actions → LinkedIn DevOps Bot → Run workflow**  
Set `dry_run` to `true` → click Run  
Check the logs — you'll see the generated post printed without publishing.

### 5. Go live

Run workflow again with `dry_run = false`.  
Or just wait — the cron fires automatically Mon–Fri.

---

## Post schedule (IST)

| Cron UTC | IST | Topic |
|---|---|---|
| 2:30 AM | 8:00 AM | CI/CD |
| 5:00 AM | 10:30 AM | Kubernetes |
| 7:30 AM | 1:00 PM | Projects |
| 10:00 AM | 3:30 PM | Debug tips |
| 12:30 PM | 6:00 PM | Charts & code |

---

## Manual trigger options

In the **Run workflow** dialog:
- **topic** — force a specific topic: `cicd`, `kubernetes`, `project`, `debug`, `charts_code`
- **dry_run** — `true` to preview without posting

---

## Token refresh (every 60 days)

LinkedIn access tokens expire after 60 days. To refresh:
1. Go back to LinkedIn Developers → OAuth 2.0 tools
2. Generate a new token
3. Update the `LINKEDIN_ACCESS_TOKEN` GitHub Secret

> Tip: set a repeating calendar event for day 55 so you never miss it.

---

## Customising the content

Edit the `PROMPTS` dictionary in `bot.py` to add your own prompt variants.  
Each topic supports multiple variants — the bot picks one deterministically  
per day so the same topic never repeats the same post in the same week.
