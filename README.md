# Blogger Auto Publishing

Automatically publish markdown blog posts to [Blogger](https://www.blogger.com) via GitHub Actions and the Blogger API v3.

## Features

- Write posts in **markdown** with YAML frontmatter for metadata
- Automatic markdown-to-HTML conversion with tables, code blocks, and more
- Duplicate detection — skips posts that already exist on your blog
- GitHub Actions trigger on push and manual dispatch
- Automatic OAuth 2.0 access token refresh

## Project Structure

```
blogger-auto/
├── posts/                    # Drop .md files here
│   └── example.md
├── publish.py                # Main publishing script
├── requirements.txt          # Python dependencies
├── README.md
└── .github/
    └── workflows/
        └── publish.yml       # GitHub Actions workflow
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

### 3. Find Your Blog ID

1. Go to your [Blogger dashboard](https://www.blogger.com/)
2. Click on the blog you want to publish to
3. Look at the URL: `https://www.blogger.com/blogger.g?blogID=YOUR_BLOG_ID`
4. Or go to **Settings** — the Blog ID is displayed there

### 4. Configure GitHub Secrets

In your GitHub repository, go to **Settings** > **Secrets and variables** > **Actions** and add these secrets:

| Secret Name     | Description                    |
|----------------|--------------------------------|
| `BLOG_ID`      | Your Blogger blog ID           |
| `CLIENT_ID`    | OAuth 2.0 Client ID            |
| `CLIENT_SECRET`| OAuth 2.0 Client Secret        |
| `REFRESH_TOKEN`| OAuth 2.0 refresh token        |

Click **New repository secret** for each one.

### 5. Write a Post

Create a `.md` file in the `posts/` directory with YAML frontmatter:

```markdown
---
title: My Amazing Blog Post
labels: Technology,Programming,Python
---

# My Amazing Blog Post

Write your content here using standard markdown.

## Subheading

- Lists work
- **Bold text** and *italics*

​```python
print("Code blocks too!")
​```

| Tables | Work |
|---------|------|
| Yes     | ✅   |
```

#### Frontmatter Fields

| Field    | Required | Description                                  |
|----------|----------|----------------------------------------------|
| `title`  | Yes      | Post title (used for duplicate detection)     |
| `labels` | No       | Comma-separated labels/categories             |

### 6. Publish

Push your markdown file to the repository. The GitHub Actions workflow triggers automatically and publishes your post to Blogger.

You can also run the workflow manually from the **Actions** tab using **workflow_dispatch**.

## Local Testing

To test locally without GitHub Actions:

```bash
# Set environment variables
export BLOG_ID="your_blog_id"
export CLIENT_ID="your_client_id"
export CLIENT_SECRET="your_client_secret"
export REFRESH_TOKEN="your_refresh_token"

# Install dependencies
pip install -r requirements.txt

# Run the publisher
python publish.py
```

## How Duplicate Detection Works

Before publishing, the script fetches all existing live posts from your blog and compares their titles (case-insensitive). If a title match is found, the post is skipped. This prevents duplicate content when the workflow re-runs.

## License

MIT
