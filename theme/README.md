# Baby Names Blogger Theme

A modern, mobile-friendly Blogger theme designed for a baby names website.

## How to Install

### Option 1: Upload via Blogger Dashboard

1. Go to [Blogger Dashboard](https://www.blogger.com/)
2. Select your blog
3. Go to **Theme** (left sidebar)
4. Click the dropdown arrow next to **Customize** → Select **Edit HTML**
5. **Backup your current theme** (click "Download" ⬇️ button)
6. Delete all existing code
7. Copy the entire contents of `baby-names-theme.xml`
8. Paste into the editor
9. Click **Save theme** (💾 icon)

### Option 2: Restore from file

1. Go to **Theme** → **Edit HTML**
2. Click **Revert** → **Upload** → Select `baby-names-theme.xml`
3. Click **Save theme**

## After Installing

1. Go to **Layout** to arrange your widgets
2. Go to **Theme** → **Customize** for color adjustments
3. Ensure **Google AdSense** is connected (Earnings → AdSense)

## Theme Features

- ✅ Blogger compatible (all standard widgets preserved)
- ✅ Mobile responsive (3 breakpoints)
- ✅ Hero section with CTA (homepage only)
- ✅ Category cards grid (10 categories, homepage only)
- ✅ Trending names section with rankings (homepage only)
- ✅ Search bar with quick-filter tags (all pages)
- ✅ Modern footer with 4-column layout
- ✅ AdSense ready (auto ads included)
- ✅ SEO optimized (meta tags, OG tags, canonical)
- ✅ Fast-loading (preconnect, lazy images, no external CSS)
- ✅ Accessible (skip link, ARIA labels)
- ✅ Print styles included
- ✅ Social sharing buttons
- ✅ Popular Posts, Labels, Archive widgets

## Widget Sections

| Section ID | Purpose |
|---|---|
| `main` | Blog posts (Blog1 widget, locked) |
| `sidebar-right-1` | Popular Posts widget |
| `sidebar-right-2` | Labels/Categories widget |
| `sidebar-right-3` | Blog Archive widget |

## Customization Tips

- **Colors**: Edit CSS variables in `<b:skin>` — look for `:root { ... }`
- **Hero text**: Edit the `<section class='hero'>` HTML block
- **Category links**: Update URLs in the category cards section
- **Trending names**: Edit the hardcoded popular names data
- **Footer links**: Update social media URLs and page links

## Labels Used

The theme references these Blogger labels for category filtering:

```
Baby Girl Names, Baby Boy Names, Gender Neutral,
Biblical, Nature, Vintage, Unique, Japanese,
Irish, Warrior, Baby Name Ideas 2026
```
