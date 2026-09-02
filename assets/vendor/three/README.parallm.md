# Three.js Runtime Subset

ParaLLM vendors the minimal Three.js files required by the Repo inspector's deterministic 3D projections.

- Package: `three`
- Version: `0.185.1`
- Source: `https://www.npmjs.com/package/three`
- Included runtime: `three.module.min.js` and its `three.core.min.js` module
- Included addon: `examples/jsm/controls/OrbitControls.js`
- License: MIT, preserved in `LICENSE`

The dependency is served locally. The Repo inspector does not require a CDN or an npm build step at runtime.
