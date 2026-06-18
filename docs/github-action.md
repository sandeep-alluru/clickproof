# GitHub Action

Use guiproof directly in your GitHub Actions workflow:

```yaml
- name: guiproof
  uses: sandeep-alluru/guiproof@v0.1.0
  with:
    # TODO: add action inputs
    fail-on-error: "true"
```

Or use the CLI directly:

```yaml
- name: Install guiproof
  run: pip install guiproof

- name: Run guiproof
  run: guiproof --help
```
