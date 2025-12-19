# Slidev Theme AWS Dark

A professional dark theme for Slidev presentations, designed with AWS branding and style guidelines.

## Features

- 🎨 AWS brand colors and gradients (Blue, Green, Purple, Orange)
- 🌙 Dark mode optimized with beautiful gradient backgrounds
- 📐 Multiple layout options (cover, section, quote, two-cols, etc.)
- 🖼️ Background images for cover and section slides
- 💼 Professional footer with AWS logo and copyright
- 📊 Big number component for statistics
- 🎯 Gradient text component for highlights

## Installation

### Local Theme (Recommended for development)

Add the following to your slides frontmatter:

```yaml
---
theme: ./theme-aws-dark
---
```

### As NPM Package (Future)

```bash
npm install slidev-theme-aws-dark
```

```yaml
---
theme: aws-dark
---
```

## Layouts

### Cover
Title slide with AWS gradient background

```yaml
---
layout: cover
sessionId: "SESSION-123"  # Optional, only shows if set
---

::title::
Your Presentation Title

::subtitle::
Your subtitle text

::speaker::
Speaker name (pronouns)

Speaker job title

Speaker company
```

Or use simple format:
```yaml
---
layout: cover
---
# Your Title
Your subtitle

Speaker info
```

The `sessionId` parameter is optional. If not provided or empty, the session ID box will not be displayed.

### Section
Section divider with gradient background. Content flows from top to bottom.
```yaml
---
layout: section
---
# Section Title

Optional subtitle or description

You can add:
- Bullet points
- Multiple paragraphs
- Any content below the title
```

### Default
Standard content slide
```yaml
---
layout: default
---
# Slide Title
Content here
```

### Center
Centered content with same styling as default layout
```yaml
---
layout: center
---
# Centered Title

Content is centered horizontally and vertically
```

### Intro
Introduction layout with subtitle support
```yaml
---
layout: intro
---
# Main Title
## Subtitle
Content here
```

### Left Right
Simple left-right two-column layout (for short content within ~10 lines)
```yaml
---
layout: left-right
---
Left column content

::right::
Right column content
```

### Two Columns
Two-column layout with title and scrollable content (for longer content)
```yaml
---
layout: two-cols
---

::title::
# Process Overview

::left::
## Step 1: Planning
Detailed planning phase...

## Step 2: Implementation
Implementation details...

::right::
## Step 3: Testing
Testing procedures...

## Step 4: Deployment
Deployment process...
```

### Image Right
Title spans full width, content on left, image on right
```yaml
---
layout: image-right
---
# Title

::left::
Content here

::right::
![Image](/path/to/image.png)
```

### End
Closing slide with AWS gradient background (blue to purple)
```yaml
---
layout: end
---
# Thank You
Questions?
```

## Components

### GradientText Component
Highlight text with gradient colors:

```html
<GradientText color="blue-green">Highlighted text</GradientText>
<GradientText color="blue-purple">Another highlight</GradientText>
<GradientText color="orange-pink">Third option</GradientText>
```

Available colors:
- `blue-green` (default): Blue to green gradient
- `blue-purple`: Blue to purple gradient
- `orange-pink`: Orange to pink gradient

### AWSLogo Component
Display AWS logo with different sizes:

```html
<AWSLogo size="sm" />
<AWSLogo size="md" />
<AWSLogo size="lg" />
<AWSLogo size="xl" />
```

## Custom CSS Classes

### Gradient Text (manual styling):
```html
<span class="gradient-text">Highlighted text</span>
```

## Assets

All assets are included in the theme's `public` folder:
- `/aws_logo.png` - AWS logo (white version)
- `/ppt-title-background.png` - Cover slide background with gradient
- `/section-title-background.png` - Section slide background with gradient

These assets are automatically available when using the theme. No need to copy them to your presentation folder.

## Mermaid Diagrams

Mermaid diagrams are styled with white lines and boxes for clarity on dark backgrounds.

### Available Arrow Styles

```mermaid
graph LR
    A --> B   %% Normal arrow (triangle)
    A -.-> B  %% Dotted arrow
    A ==> B   %% Thick arrow
    A --o B   %% Circle end
    A --x B   %% Cross end
    A --- B   %% No arrow (line only)
    A <--> B  %% Bidirectional arrow
```

**Syntax:**
- `-->` Normal arrow with triangle head (default)
- `-.->` Dotted line with arrow
- `==>` Thick line with arrow
- `--o` Line with circle end
- `--x` Line with cross end
- `---` Line without arrow
- `<-->` Bidirectional arrow

For AWS architecture diagrams, use `-->` for standard connections or `---` for line-only connections.

## Colors

- AWS Orange: `#ff9900`
- AWS Blue: `#00a1e0`
- AWS Green: `#00d4aa`
- AWS Purple: `#9d4edd`
- Dark Blue: `#232f3e`
- Content Background: `#000000` (pure black)
- Special Slides (cover/section/end): Gradient backgrounds

## Customization

### Theme Colors and Styles

You can customize the theme by adding CSS variables to your presentation:

```yaml
---
theme: ../theme-aws-dark
---

<style>
:root {
  /* Change background color */
  --theme-background: rgb(30, 40, 54);
  
  /* Change text color */
  --theme-text: #f0f0f0;
  
  /* Change brand colors */
  --aws-blue: #0099ff;
  --aws-orange: #ff6600;
  
  /* Change font sizes */
  --theme-font-size-h1: 3.5rem;
  --theme-font-size-h2: 2.5rem;
}
</style>

# Your Presentation
```

See [CUSTOMIZATION.md](./CUSTOMIZATION.md) for detailed customization guide.

See [BACKGROUND-GUIDE.md](./BACKGROUND-GUIDE.md) for complete background customization guide.

### Available CSS Variables

**Background Variables:**
- `--theme-background`: Content slides background (default: #000000)
- `--theme-gradient-cover`: Cover slide gradient
- `--theme-gradient-section`: Section slide gradient
- `--theme-gradient-end`: End slide gradient

**Color Variables:**
- `--theme-text`: Main text color
- `--aws-blue`, `--aws-orange`, `--aws-green`: Brand colors

**Typography Variables:**
- `--theme-font-size-h1`, `--theme-font-size-h2`, etc.: Font sizes

**Spacing Variables:**
- `--theme-padding`: Slide padding
- `--theme-gap`: Column gap

### Predefined Background Classes

Apply gradient backgrounds to any slide using CSS classes:

```yaml
---
layout: center
class: bg-ocean
---

# Ocean Themed Slide
```

**AWS Gradient Classes:**
- `bg-aws-default`, `bg-aws-blue`, `bg-aws-orange`, `bg-aws-green`, `bg-aws-purple`

**Theme Gradient Classes:**
- `bg-ocean` (professional), `bg-sunset` (warm), `bg-forest` (natural)
- `bg-night` (elegant), `bg-fire` (bold), `bg-royal` (luxury), `bg-tech` (modern)

**Solid Color Classes:**
- `bg-black`, `bg-dark-gray`, `bg-dark-blue`, `bg-aws-dark-blue`

See [CUSTOMIZATION.md](./CUSTOMIZATION.md) for complete guide and examples.
