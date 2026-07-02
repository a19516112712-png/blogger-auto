# Enhance Your Contempo Theme — Step-by-Step Installation

Each step adds one piece. You can stop at any point and everything still works. No XML editing required — all via the Blogger dashboard.

---

## Step 1: Add Custom CSS

1. Go to **Blogger Dashboard** → **Theme**
2. Click **Customize** (orange button)
3. In the left panel, scroll down to **Advanced** → **Add CSS**
4. Open the file **`custom-css.css`** from this folder
5. Copy the **entire contents** and paste into the CSS box
6. Click **Apply to Blog** (top-right)

> This adds all styling for hero, cards, popular names, footer, search bar, and post enhancements.

---

## Step 2: Add Hero + Navigation + Search Widget

1. Go to **Blogger Dashboard** → **Layout**
2. Find the area **above the Header** (or inside the Header section)
3. Click **Add a Gadget** → choose **HTML/JavaScript**
4. Set **Title**: leave blank (or type "Navigation")
5. Open **`widget-hero.html`** and copy the entire contents
6. Paste into the gadget's **Content** box
7. Click **Save**
8. Drag the gadget to the very top of your layout if needed

> This adds: sticky navigation bar, mobile hamburger menu, hero section with CTA, and search bar.

---

## Step 3: Add Category Cards Widget

1. Go to **Blogger Dashboard** → **Layout**
2. Find the area **below the Header** but **above Blog Posts**
3. Click **Add a Gadget** → choose **HTML/JavaScript**
4. Set **Title**: "Browse by Category"
5. Open **`widget-category-cards.html`** and copy the entire contents
6. Paste into the gadget's **Content** box
7. Click **Save**

> 10 category cards linking to label search pages. Only visible on homepage (Contempo will show it on all pages — that's fine).

---

## Step 4: Add Popular Names Widget

1. Go to **Blogger Dashboard** → **Layout**
2. Click **Add a Gadget** below the Category Cards
3. Choose **HTML/JavaScript**
4. Set **Title**: "Trending Right Now"
5. Open **`widget-popular-names.html`** and copy the entire contents
6. Paste into the gadget's **Content** box
7. Click **Save**

> 8 ranked popular name cards with meanings. Links to search for each name.

---

## Step 5: Add Enhanced Footer Widget

1. Go to **Blogger Dashboard** → **Layout**
2. Scroll to the **Footer** section at the bottom
3. Click **Add a Gadget** → choose **HTML/JavaScript**
4. Set **Title**: leave blank
5. Open **`widget-footer.html`** and copy the entire contents
6. Paste into the gadget's **Content** box
7. Click **Save**

> 4-column footer with about blurb, browse links, origin links, resources, and social icons.

---

## Step 6: Configure Sidebar Widgets (Optional)

1. Go to **Layout** → find the **Sidebar** section
2. Add or configure these native Blogger widgets:
   - **Popular Posts**: Show 5 items, thumbnails ON, snippets ON, ALL TIME
   - **Labels**: Show as LIST, sort ALPHABETICALLY, show counts ON
   - **Blog Archive**: HIERARCHY style, show counts ON

---

## Step 7: Connect AdSense (Optional)

1. Go to **Blogger Dashboard** → **Earnings**
2. Click **Sign up for AdSense** or **Connect existing account**
3. Once approved, Blogger auto-places ads
4. The theme CSS already has `.bn-adslot` styling for ad containers

---

## Layout Reference (After Installation)

```
┌─────────────────────────────────────┐
│  HERO Widget (nav + hero + search)  │  ← Step 2
├─────────────────────────────────────┤
│  CATEGORY CARDS Widget              │  ← Step 3
├─────────────────────────────────────┤
│  POPULAR NAMES Widget               │  ← Step 4
├──────────────────┬──────────────────┤
│  BLOG POSTS      │  SIDEBAR         │
│  (native)        │  - Popular Posts │
│                  │  - Labels        │
│                  │  - Archive       │
├──────────────────┴──────────────────┤
│  FOOTER Widget                      │  ← Step 5
│  (native footer complement)         │
└─────────────────────────────────────┘
```

---

## Files in This Folder

| File | Purpose | Where to paste |
|---|---|---|
| `custom-css.css` | All styling (605 lines) | Theme → Customize → Advanced → Add CSS |
| `widget-hero.html` | Nav + Hero + Search | Layout → HTML/JavaScript gadget (top) |
| `widget-category-cards.html` | 10 category cards | Layout → HTML/JavaScript gadget |
| `widget-popular-names.html` | 8 trending name cards | Layout → HTML/JavaScript gadget |
| `widget-footer.html` | 4-column footer | Layout → HTML/JavaScript gadget (footer) |

---

## Troubleshooting

**Widgets look wrong or unstyled?**
→ Make sure Step 1 (Custom CSS) was saved correctly. CSS must be applied first.

**Hero/header overlaps with Contempo header?**
→ In Layout, move the Hero widget above the Header section, or disable the Contempo header image in Theme → Customize → Background.

**Mobile menu not working?**
→ Check that the `<script>` block at the bottom of `widget-hero.html` was included. It contains the `bnToggleMenu()` function.

**Footer duplicates the Contempo footer?**
→ You can hide Contempo's default footer by going to Theme → Edit HTML, finding the footer section, and wrapping it with `<!--` and `-->`. Or simply remove the native footer widget from Layout.

**Search returns no results?**
→ Search works based on your published post content. If you haven't published articles yet, it will show "no results." The search uses Blogger's built-in `/search?q=` endpoint — no setup needed.

---

## Need to Update Social Links?

Edit in these files:
- **Footer social links**: `widget-footer.html` (lines ~24-28, look for `href="https://pinterest.com"`)
- **Navigation links**: `widget-hero.html` (lines ~11-18)
- **Category links**: `widget-category-cards.html` (each card's `href`)
