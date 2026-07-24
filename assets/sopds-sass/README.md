# SOPDS frontend assets

Install the pinned dependencies and rebuild the checked-in static assets:

```shell
npm ci
npm run build
```

The Sass entry point is `scss/sopds.scss`. The build also copies the required
browser libraries from `node_modules` to `web_backend/static/js/vendor`.
Generated files under `web_backend/static` are intentionally ignored by Git.

For local development, keep the Sass compiler running in a separate terminal:

```shell
make frontend-dev
```
