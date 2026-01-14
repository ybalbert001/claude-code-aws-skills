# Layouts Demo

This section demonstrates all available layouts.

---
layout: intro
---

# Intro Layout

## Subtitle Goes Here

This layout is perfect for introducing new topics or sections. It provides a clean, focused presentation of your content with proper hierarchy.

Use it when you need more text than a section slide but want to maintain visual impact.

<!--
Intro layout is between section and default - more content than section, cleaner than default.
-->

---
layout: intro
class: bg-aws-dark-blue
---

# AWS Dark Blue Background

## A Professional Alternative

This slide uses `class: bg-aws-dark-blue` (#141e2c)

Perfect for a softer, more professional look than pure black while maintaining the dark theme aesthetic.

Great for corporate presentations or when you want a subtle background.

<!--
Demonstrates AWS dark blue background - a professional alternative to pure black.
-->

---
layout: default
---

# Default Layout

This is the standard content layout with:

- Clean, readable text
- Proper spacing
- AWS branding in footer
- Page numbers

Perfect for most content slides with text, lists, and code.

<!--
Default layout is the workhorse - use it for most content slides.
-->

---
layout: two-cols
---

::title::
# Two-cols layout

::left::

## Left Column

- Point 1
- Point 2
- Point 3

This layout has a title and two scrollable columns.

::right::

## Right Column

- Feature A
- Feature B
- Feature C

Perfect for comparisons or detailed content.

<!--
Two-cols layout with title and scrollable columns for longer content.
-->

---
layout: left-right
---

# Left Column

Left column content:

- Feature A
- Feature B
- Feature C

Perfect for comparisons or side-by-side content.

::right::

# Right Column

Right column content:

- Benefit 1
- Benefit 2
- Benefit 3

Both columns are equal width.

<!--
Two-column layout is great for comparisons, before/after, or complementary content.
-->

---
layout: image-right
---

# Image Right Layout

::left::

Content on the left, image on the right.

- Perfect for visual storytelling
- Supports any image size
- Maintains aspect ratio
- Great for architecture diagrams

::right::

![City Landscape](https://d1.awsstatic.com/onedam/marketing-channels/website/aws/en_US/solution-case-studies/approved/images/gcrp-case-study-images/City%20landscape.b396337462b85cb051f37f5799dfd81a91bfbf8e.jpeg)

<!--
Image-right layout: title spans full width, content splits into left/right columns.
-->

---

# Inline Images

You can also use images inline within any layout:

![AWS City](https://d1.awsstatic.com/onedam/marketing-channels/website/aws/en_US/solution-case-studies/approved/images/gcrp-case-study-images/City%20landscape.b396337462b85cb051f37f5799dfd81a91bfbf8e.jpeg){width=600px}

Use `{width=XXXpx}` to control image size.

<!--
Inline images work in any layout. Control size with width parameter.
-->

---
layout: left-right
---

# Text Content

Combine text and images in columns:

- Cloud infrastructure
- Scalable solutions
- Global reach
- High availability

::right::

![City Infrastructure](https://d1.awsstatic.com/onedam/marketing-channels/website/aws/en_US/solution-case-studies/approved/images/gcrp-case-study-images/City%20landscape.b396337462b85cb051f37f5799dfd81a91bfbf8e.jpeg){width=100%}

<!--
Left-right layout also works great with images in either column.
-->
