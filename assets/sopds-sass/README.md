# SOPDS frontend assets

Install the pinned dependencies and build the minified runtime assets:

```shell
npm ci
npm run build
```

The Sass entry point is `scss/sopds.scss`. The build also copies the required
browser libraries from `node_modules` to `web_backend/static/js/vendor`.
Generated CSS and browser libraries under `web_backend/static` are
intentionally ignored by Git. The Docker frontend stage performs the same
build before Django runs `collectstatic`; neither Node.js nor the source static
directory is included in the runtime image.

For local development, run the watcher from the repository root in a separate
terminal:

```shell
make frontend-dev
```
