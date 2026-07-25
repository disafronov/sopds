# SOPDS frontend assets

Install the pinned dependencies and build the minified runtime assets:

```shell
npm ci
npm run build
```

The Sass entry point is `scss/sopds.scss`. The build also copies the required
browser libraries from `node_modules` to `web_frontend/static/js`.
Generated CSS and browser libraries under `web_frontend/static` are
intentionally ignored by Git. The Docker frontend stage performs the same
build before Django runs `collectstatic`; neither Node.js nor the source static
directory is included in the runtime image.

The generated `sopds.min.js` bundle contains the browser-side OPDS client used
by `/web/`; JavaScript must be enabled for the web catalog to load its feeds.

For local development, run the watcher from the repository root in a separate
terminal:

```shell
make frontend-dev
```
