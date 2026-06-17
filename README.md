# Blogger Auto Publishing

Automatically generate SEO-optimized baby-name articles with Agnes AI, then publish them to [Blogger](https://www.blogger.com) via GitHub Actions and the Blogger API v3.

## Features

- **AI Content Generation** — Agnes AI writes 5 SEO articles per day about baby names
- **Markdown with YAML frontmatter** — title, labels, and meta descriptions included
- **Automatic markdown-to-HTML conversion** — tables, code blocks, headings, and more
- **Duplicate detection** — skips posts that already exist on your blog
- **Dual GitHub Actions workflows** — one for daily generation, one for publishing on push
- **Automatic OAuth 2.0 access token refresh**

## Project Structure

```
blogger-auto/
├── posts/                       # Generated and manual .md files
│   └── example.md
├── generate_content.py          # Agnes AI-powered article generator
├── publish.py                   # Blogger API publisher
├── requirements.txt             # Python dependencies
├── README.md
└── .github/
    └── workflows/
        ├── generate.yml          # Daily cron: generate 5 articles, commit
        └── publish.yml           # On push: publish to Blogger
```

## How It Works

```
Daily cron (midnight UTC)
    │
    ▼
generate.yml ──► generate_content.py ──► Agnes AI
                                              │
                                       5 new .md files in posts/
                                              │
                                     auto-commit & push
                                              │
                                              ▼
                                    publish.yml triggered
                                              │
                                              ▼
                                    publish.py ──► Blogger API
                                                      │
                                               Posts published
```

## Getting Started

### 1. Get Blogger API Credentials

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select an existing one)
3. Navigate to **APIs & Services** > **Library**
4. Search for **Blogger API v3** and enable it
5. Go to **APIs & Services** > **Credentials**
6. Click **Create Credentials** > **OAuth 2.0 Client ID**
7. Set **Application type** to **Web application**
8. Name it (e.g. "Blogger Auto Publish")
9. Add `https://developers.google.com/oauthplayground` as an **Authorized redirect URI**
10. Click **Create** — you'll see your **Client ID** and **Client Secret**

### 2. Get a Refresh Token

1. Open the [OAuth 2.0 Playground](https://developers.google.com/oauthplayground)
2. Click the gear icon ⚙️ (settings) and check **Use your own OAuth credentials**
3. Enter your **Client ID** and **Client Secret**, then close settings
4. In Step 1 (Select & authorize APIs), find **Blogger API v3** and select the `https://www.googleapis.com/auth/blogger` scope
5. Click **Authorize APIs**, sign in with your Google account, and grant access
6. In Step 2, click **Exchange authorization code for tokens**
7. Copy the **Refresh token** shown

### 3. Get an Agnes AI API Key

1. Go to [Agnes AI Hub](https://hub.agnes-ai.com)
2. Sign up or log in to your account
3. Navigate to **API Keys** in your dashboard
4. Click **Create API Key** and copy it

### 4. Find Your Blog ID

1. Go to your [Blogger dashboard](https://www.blogger.com/)
2. Click on the blog you want to publish to
3. Look at the URL: `https://www.blogger.com/blogger.g?blogID=YOUR_BLOG_ID`

### 5. Configure GitHub Secrets

In your GitHub repository, go to **Settings** > **Secrets and variables** > **Actions** and add these secrets:

| Secret Name       | Description                          |
|-------------------|--------------------------------------|
| `BLOG_ID`         | Your Blogger blog ID                 |
| `CLIENT_ID`       | OAuth 2.0 Client ID                  |
| `CLIENT_SECRET`   | OAuth 2.0 Client Secret              |
| `REFRESH_TOKEN`   | OAuth 2.0 refresh token              |
| `AGNES_API_KEY`   | Agnes AI API key from dashboard       |
| `AGNES_MODEL`     | Model name (default: Agnes 2.0 Flash)  |

### 6. Write (or Generate) a Post

**Manual posts** — Create a `.md` file in `posts/`:

```markdown
---
title: My Amazing Blog Post
labels: Technology,Programming,Python
---

# My Amazing Blog Post

Write your content here using standard markdown.
```

**Auto-generated posts** — The `generate.yml` workflow runs daily and creates 5 SEO-optimized baby-name articles. Each generated article includes:

- Engaging, SEO-friendly title
- Meta description for search snippets
- H2/H3 heading hierarchy
- Lists, comparisons, and bolded key terms
- FAQ section with 4-5 detailed Q&A pairs
- 800-1200 words per article

#### Frontmatter Fields

| Field              | Required | Description                                  |
|--------------------|----------|----------------------------------------------|
| `title`            | Yes      | Post title (used for duplicate detection)     |
| `labels`           | No       | Comma-separated labels/categories             |
| `meta_description` | No       | SEO meta description (auto-generated posts)   |

### 7. Publish

For manual posts, push your `.md` file to the repository. For generated posts, the daily cron handles everything — generation, commit, and publishing — automatically.

You can also trigger either workflow manually from the **Actions** tab:
- **Generate Baby Name Articles** — generates 5 new articles via Agnes AI
- **Publish to Blogger** — publishes any un-published posts in `posts/`

## Workflows

| Workflow | Trigger | What It Does |
|----------|---------|--------------|
| `generate.yml` | Daily cron (`0 0 * * *`) or manual | Generates 5 articles via Gemini, commits them |
| `publish.yml` | Push to `posts/*.md` or manual | Publishes new posts to Blogger |

## Local Testing

```bash
# Set environment variables
export BLOG_ID="your_blog_id"
export CLIENT_ID="your_client_id"
export CLIENT_SECRET="your_client_secret"
export REFRESH_TOKEN="your_refresh_token"
export AGNES_API_KEY="your_agnes_api_key"

# Install dependencies
pip install -r requirements.txt

# Optional: set model (defaults to Agnes 2.0 Flash)
# export AGNES_MODEL=Agnes 2.0 Flash

# Generate articles
python generate_content.py

# Publish to Blogger
python publish.py
```

## How Duplicate Detection Works

Before publishing, `publish.py` fetches all existing live posts from your blog and compares their titles (case-insensitive). If a title match is found, the post is skipped.

Generated articles include a date prefix in the filename (`2026-06-16-slug.md`) to avoid collisions. The script also appends a counter if a filename already exists.

## License

MIT
