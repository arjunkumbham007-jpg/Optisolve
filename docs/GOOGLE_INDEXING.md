# Getting OptiSolve discovered by Google

A website can be public and working without appearing immediately in search results. Google decides whether and when to crawl, index, and rank a site; submitting it does not guarantee inclusion or a particular position.

## Before requesting indexing

1. Deploy OptiSolve to a publicly reachable HTTPS URL on a domain you own.
2. Set `OPTISOLVE_BASE_URL` to the exact canonical origin, for example `https://your-real-domain.example` (replace the example with your actual domain).
3. Confirm these URLs work in a browser:
   - `/`
   - `/about`
   - `/privacy`
   - `/robots.txt`
   - `/sitemap.xml`
4. Inspect the HTML source for a descriptive title, meta description, canonical URL, and WebApplication structured data. Canonical and structured data only include the public URL when `OPTISOLVE_BASE_URL` is set.
5. Keep the visible explanation honest about what the product does and its limits. Don't claim general business-story AI understanding or production-scale performance.

## Google Search Console

1. Open Google Search Console while signed into the Google account you want to use.
2. Add a **Domain property** for the domain. Follow the current verification instructions in Search Console; domain properties typically use a DNS TXT record managed at your DNS provider.
3. After verification, submit the sitemap URL: `https://your-real-domain.example/sitemap.xml`.
4. Use URL Inspection for the homepage and `/about`, and request indexing when the URL is eligible.
5. Recheck indexing and coverage reports over time. Google may take days or longer to crawl/index a new site, and submission is not a guarantee.

## Ranking for the word “OptiSolve”

The product name may overlap with other names or pages. Don't expect a top position simply because the site title contains “OptiSolve.” Use a descriptive page title such as “OptiSolve — Interactive Linear Programming Solver & Simplex Visualizer,” provide useful original documentation and demos, and share the canonical URL from your GitHub repository, portfolio, and relevant educational communities. Avoid keyword stuffing and fake backlinks.

## Privacy and job videos

The sitemap lists only the homepage, About, and Privacy pages. Solver endpoints and generated job videos are disallowed in `robots.txt`; video responses additionally send `X-Robots-Tag: noindex, nofollow`. Job artifacts are temporary and are served through unguessable job-specific paths until cleanup.
