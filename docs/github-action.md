# GitHub Action

Use clickproof directly in your GitHub Actions workflow:

```yaml
- name: clickproof
  uses: sandeep-alluru/clickproof@v0.1.0
  with:
    # TODO: add action inputs
    fail-on-error: "true"
```

Or use the CLI directly:

```yaml
- name: Install clickproof
  run: pip install clickproof

- name: Run clickproof
  run: clickproof --help
```
