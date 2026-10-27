# The Redis that agent events stream through, for the catalog's `redis` component. The
# registry builds every component image from this repository, so the base is pinned here.
FROM redis:7-alpine
