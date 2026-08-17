# TechWithKoushik Video Site Builder

This builder reads one `video.txt` file per certification series and generates:

- `/videos/<series>/index.html` — one landing page per certification
- `/videos/<series>/set-XX.html` — one dedicated watch page per YouTube video
- `/sitemap.xml` — normal sitemap for your website pages
- `/video-sitemap.xml` — Google video sitemap

## Build

Run:

```bash
python generate_video_pages.py --clean
```

No third-party Python packages are required.

## Configured series

- AIF-C01
- CLF-C02
- DVA-C02
- SAA-C03
- AZ-104
- AZ-305
- AZ-400
- AZ-900
- SC-100

## Updating later

1. Edit or replace `video_data/<series>/video.txt`.
2. Run the generator again.
3. Upload the regenerated `videos/`, `sitemap.xml`, and `video-sitemap.xml`.

## AI & Machine Learning + Certification Study Guides

The builder also reads `video2.txt` and automatically generates two additional libraries:

- `videos/ai-machine-learning/`
- `videos/exam-study-guides/`

`video2.txt` uses section headings followed by `Title | YouTube URL` rows. Example:

```text
AI & Machine Learning Videos
Vector Database Explained | https://www.youtube.com/watch?v=VIDEO_ID

Certification Study Guide Videos
SC-100 Study Guide 2026 | https://www.youtube.com/watch?v=VIDEO_ID
```

For each row, the generator creates a dedicated HTML watch page and adds it to both `sitemap.xml` and `video-sitemap.xml`. The section `index.html` page is also generated automatically.
