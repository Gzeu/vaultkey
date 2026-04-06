# PyPI Trusted Publisher Configuration

To enable automatic PyPI publishing via GitHub Actions (no API token needed):

## 1. Add Trusted Publisher in PyPI

1. Go to: https://pypi.org/manage/project/vaultkey/settings/publishing/
2. Click "Add a new publisher"
3. Use these settings:
   - Publisher name: GitHub Actions
   - Owner: Gzeu
   - Repository: vaultkey
   - Workflow name: .github/workflows/release.yml
   - Environment: (leave blank)

## 2. Verify GitHub Actions Permissions

Ensure your repository has:
- Settings → Actions → General → Workflow permissions: "Read and write permissions"
- Settings → Actions → General → Allow GitHub Actions to create and approve pull requests: ✅

## 3. Test Release

Create a new tag:
```bash
git tag v1.2.1
git push origin v1.2.1
```

This will trigger the release workflow automatically.
