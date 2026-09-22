# Self_Guided_Lectures_330

ENRG 330 supplemental self-guided lectures: one interactive walk-through per
lecture. Each restates a key point from the lecture and steps students through
problems they must answer to unlock the next screen.

Live site (after GitHub Pages is turned on):
https://dglosser.github.io/Self_Guided_Lectures_330/

`index.html` is **generated**. Do not edit it by hand. `build_index.py` scans the
repo, reads the meta tags out of each lecture file, and rewrites the index. A
GitHub Action reruns it on every push.

Answer keys (`*_KEY.html`) are deliberately **not** in this repo. They live in
Box (`ENRG 330/Ordered lectures/Self-guided`). `.gitignore` blocks them, so
copying the whole Box folder in by accident won't publish them.

---

## Adding or updating a lecture

1. Drop the new or edited `lectureNs_slug.html` into the repo root.
2. Check the three meta tags at the top of the `<head>`:

   ```html
   <meta name="lecture-number" content="16s">
   <meta name="lecture-title" content="Short Title">
   <meta name="lecture-topic" content="One-line description">
   ```

3. Commit and push. The index rebuilds itself.

`lecture-number` is digits plus an optional letter suffix (`7`, `7s`, `7a`).
If the meta tag is missing, the number and title fall back to the filename
(`lecture7s_slug.html` gives 7s). A file with neither lands in an
**Unfiled** section at the bottom of the index, with a warning printed by the
build script. `template/lecture-template.html` is a blank starting point.

---

## Running the build by hand

From the repo root, in Windows Terminal / PowerShell:

```
py build_index.py
```

(Use `py`, not `python`.) Standard library only. Output is deterministic, so the
Action only commits when the index actually changes.

---

## The GitHub Action

`.github/workflows/build-index.yml` runs on every push to `main` (or by hand
from the **Actions** tab). Two things in it look optional and are not:

- `permissions: contents: write`: without it the push step fails with a 403.
- It relies on the default `GITHUB_TOKEN`, whose commits don't trigger new
  runs. Swapping in a personal access token would cause an infinite loop.

---

## GitHub Pages

Settings → Pages → Source: *Deploy from a branch*, branch `main`, folder `/ (root)`.
The generated `index.html` becomes the landing page. Every lecture is a single
self-contained HTML file with no external assets, so nothing else is needed.
