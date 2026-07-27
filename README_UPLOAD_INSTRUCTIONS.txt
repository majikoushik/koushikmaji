TechWithKoushik SEO Site Package
================================

Upload these files to the root of your CloudFront/S3 website:
- index.html
- ai-cloud-engineer-guide.html
- ai-security-cheat-sheet.html
- mcp-agentic-ai-guide.html
- ai-certifications-roadmap.html
- youtube-resources.html
- styles.css
- script.js
- robots.txt
- sitemap.xml

Create this folder in your web root if not already present:
- /pdfs/

Put your actual PDF files there with these exact names, or update the links in each HTML file:
- AI-Cloud-Engineer-Study-Guide.pdf
- AI-Security-Cheat-Sheet.pdf
- MCP-Agentic-AI-Guide.pdf
- AI-Certifications-Roadmap.pdf

After upload:
1. Open https://koushikmaji.com/sitemap.xml and confirm it loads.
2. Open https://koushikmaji.com/robots.txt and confirm it references the sitemap.
3. In Google Search Console, submit: https://koushikmaji.com/sitemap.xml
4. Use URL Inspection for each new page and request indexing.
5. Invalidate CloudFront cache for /* if your old files are cached.
