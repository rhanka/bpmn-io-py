# Upstream oracle

`package.json` pins the exact upstream JS versions this repository transposes. Python tests marked
`@pytest.mark.oracle` run the JS implementation through Node (`npm ci --ignore-scripts` here first)
and compare canonical dumps with the Python port. They are skipped when Node or `node_modules` are
absent, and mandatory in CI.
