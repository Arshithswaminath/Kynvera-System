# Image Generation Prompt — Hiring Document Tracker Dashboard

## Main Prompt (paste as-is)

iOS mobile app UI mockup, light mode, clean Apple-style design, SF Pro font. Screen titled "Hiring — Documents" with a search bar below. A scrollable list of candidate cards (white, rounded corners, soft shadow) on a light-gray background, each showing: circular initials avatar, candidate name and role, a progress bar showing document completion (e.g. "3/5"), and a colored status pill (green Complete / orange In Progress / gray Not Started). Floating blue "+" button bottom-right. Bottom tab bar with Dashboard, Candidates, Documents, Settings icons, Dashboard highlighted in iOS blue (#007AFF). Realistic iPhone status bar on top. Minimal, native iOS 17 look, rounded corners, generous white space, product mockup quality, ultra sharp.

## Negative Prompt (if your tool supports it)

blurry text, distorted UI, dark mode, cluttered layout, Android UI, skeuomorphic textures, cartoonish, low resolution, extra fingers, watermark, glare, misspelled words

## Documents Being Tracked (for reference / legend if generating a second detail screen)

1. Passport copy (colour)
2. Emirates ID copy (colour)
3. Photograph — white background, PDF
4. PCC (Police Clearance Certificate) — attested
5. Education certificate — PDF

## Optional Follow-up Prompt (detail/upload screen)

An iOS mobile app UI mockup, light mode, showing a candidate's document checklist detail screen titled with the candidate's name at the top and a back chevron. Below it, five white rounded list rows, one per document: "Passport Copy (Colour)", "Emirates ID Copy (Colour)", "Photograph (White Background, PDF)", "PCC — Attested", "Education Certificate (PDF)". Each row has a document-type icon on the left, the label in the middle, and on the right either a green checkmark with "Uploaded" if complete, or a blue outlined "Upload" button with an upward arrow icon if missing. A progress ring at the top shows overall completion percentage. Same iOS 17 light design language, SF Pro font, rounded cards, soft shadows, iOS system blue accents, realistic status bar, ultra sharp, product mockup quality.

## Tips

- Works well in Midjourney (add `--ar 9:19 --v 6` for a phone aspect ratio), DALL·E 3, or Stable Diffusion with an iOS UI LoRA.
- Image models often garble small text — expect to clean up labels in Figma/Photoshop afterward, or use this prompt purely as a layout/style reference.
- Generate the two prompts separately and stitch them side-by-side to show the list → detail flow.
