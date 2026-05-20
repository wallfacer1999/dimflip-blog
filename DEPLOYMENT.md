# Dimflip Blog Deployment

## GitHub

Create a new GitHub repository named `dimflip-blog`, then push this local repository:

```bash
git remote add origin git@github.com:<owner>/dimflip-blog.git
git push -u origin main
```

The Butterfly theme is vendored under `themes/butterfly/`; it is not a submodule.

## Cloudflare Pages

Use the Cloudflare account `Wallfacer1999@gmail.com's Account`.

Create a Pages project:

- Project name: `dimflip-blog`
- Source: GitHub repository `dimflip-blog`
- Production branch: `main`
- Build command: `npm ci && npm run build`
- Build output directory: `public`
- Environment variable: `NODE_VERSION=20`

Then add the custom domain:

- `blog.dimflip.xyz`

Do not bind or redirect the root domain `dimflip.xyz`.

After GitHub is connected, pushes to `main` trigger production deployments through Cloudflare Pages Git integration.
