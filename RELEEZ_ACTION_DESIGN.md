# Releez GitHub Action - Design Specification

## Overview

A unified GitHub composite action that provides all releez functionality for
CI/CD workflows, replacing multiple separate actions with a single configurable
action.

**Repository**: `hotdog-werx/releez-action` (new)

**Replaces**:

- `hotdog-werx/releez-finalize-action@v0` → `mode: finalize`
- `hotdog-werx/releez-version-artifact-action` → `mode: version-artifact`
- (new) → `mode: validate`

## Key Design Principles

1. **Single Action, Multiple Modes**: One action with a `mode` parameter instead
   of separate actions
2. **Safe Branch Parsing**: Uses `releez release detect-from-branch` internally
   for secure branch name parsing
3. **Monorepo Support**: Fully compatible with both single-repo and monorepo
   workflows
4. **JSON-First**: Outputs structured JSON for reliable parsing in workflows
5. **Backwards Compatible**: Works with existing single-repo setups without
   changes

## Action Modes

### Mode: `finalize`

**Purpose**: Finalize a merged release PR by creating git tags and generating
outputs.

**Trigger**: `pull_request.types.closed` when PR is merged from a release branch

**Workflow**:

1. Detect if PR is a release (branch matches `release/*` pattern)
2. Parse branch name using `releez release detect-from-branch` to extract:
   - Version (e.g., `1.2.3` or `core-1.2.3`)
   - Project name (if monorepo)
3. Run `releez release tag` to create git tags
4. Generate version outputs in multiple formats
5. Return release notes and metadata

**Inputs**:

```yaml
mode:
  description: 'Action mode'
  required: true
  # Must be: 'finalize'

is-full-release:
  description: 'Whether this is a full release (not a prerelease)'
  required: false
  default: 'true'

alias-versions:
  description: 'Alias version strategy: none, major, minor'
  required: false
  default: 'none'

dry-run:
  description: 'Run without creating tags (for testing)'
  required: false
  default: 'false'
```

**Outputs**:

```yaml
release-version:
  description: 'The release version (e.g., "1.2.3" or "core-1.2.3")'
  value: ${{ steps.detect.outputs.version }}

project:
  description: 'Project name for monorepo releases (empty for single-repo)'
  value: ${{ steps.detect.outputs.project }}

release-notes:
  description: 'Markdown release notes'
  value: ${{ steps.notes.outputs.content }}

# Artifact version outputs (JSON arrays)
semver-versions:
  description: 'JSON array of semver versions: ["1.2.3", "v1"] (with aliases)'
  value: ${{ fromJson(steps.versions.outputs.json).semver }}

docker-versions:
  description: 'JSON array of docker versions: ["1.2.3", "v1"] (with aliases)'
  value: ${{ fromJson(steps.versions.outputs.json).docker }}

pep440-versions:
  description: 'JSON array of PEP440 versions: ["1.2.3"] (no aliases)'
  value: ${{ fromJson(steps.versions.outputs.json).pep440 }}

# Legacy single-value outputs (for backwards compatibility)
semver-version:
  description: 'Primary semver version (first in array)'
  value: ${{ fromJson(steps.versions.outputs.json).semver[0] }}

docker-version:
  description: 'Primary docker version (first in array)'
  value: ${{ fromJson(steps.versions.outputs.json).docker[0] }}

pep440-version:
  description: 'Primary PEP440 version (first in array)'
  value: ${{ fromJson(steps.versions.outputs.json).pep440[0] }}
```

**Implementation Steps**:

```yaml
steps:
  # 1. Detect release from branch
  - name: Detect release information
    id: detect
    shell: bash
    run: |
      RELEASE_INFO=$(releez release detect-from-branch --branch "${{ github.head_ref }}")
      echo "version=$(echo $RELEASE_INFO | jq -r '.version')" >> $GITHUB_OUTPUT
      echo "project=$(echo $RELEASE_INFO | jq -r '.project // ""')" >> $GITHUB_OUTPUT
      echo "branch=$(echo $RELEASE_INFO | jq -r '.branch')" >> $GITHUB_OUTPUT

  # 2. Create git tags
  - name: Create release tags
    id: tag
    if: inputs.dry-run != 'true'
    shell: bash
    run: |
      PROJECT_FLAG=""
      if [ -n "${{ steps.detect.outputs.project }}" ]; then
        PROJECT_FLAG="--project ${{ steps.detect.outputs.project }}"
      fi

      releez release tag \
        --version-override "${{ steps.detect.outputs.version }}" \
        --alias-versions "${{ inputs.alias-versions }}" \
        $PROJECT_FLAG

  # 3. Generate release notes
  - name: Generate release notes
    id: notes
    shell: bash
    run: |
      PROJECT_FLAG=""
      if [ -n "${{ steps.detect.outputs.project }}" ]; then
        PROJECT_FLAG="--project ${{ steps.detect.outputs.project }}"
      fi

      NOTES=$(releez release notes \
        --version-override "${{ steps.detect.outputs.version }}" \
        $PROJECT_FLAG)

      # Multi-line output handling
      {
        echo "content<<EOF"
        echo "$NOTES"
        echo "EOF"
      } >> $GITHUB_OUTPUT

  # 4. Generate artifact versions (JSON)
  - name: Generate artifact versions
    id: versions
    shell: bash
    run: |
      # Use unified JSON output (no --scheme specified)
      VERSIONS_JSON=$(releez version artifact \
        --version-override "${{ steps.detect.outputs.version }}" \
        --is-full-release=${{ inputs.is-full-release }} \
        --alias-versions "${{ inputs.alias-versions }}")

      # Output as JSON for parsing
      {
        echo "json<<EOF"
        echo "$VERSIONS_JSON"
        echo "EOF"
      } >> $GITHUB_OUTPUT
```

### Mode: `validate`

**Purpose**: Validate a release PR before merge (dry-run preview).

**Trigger**: `pull_request.types.[opened, reopened, synchronize]` on release
branches

**Workflow**:

1. Detect release from branch name
2. Run `releez release preview --dry-run`
3. Output preview and validation status
4. Optionally post PR comment with preview

**Inputs**:

```yaml
mode:
  description: 'Action mode'
  required: true
  # Must be: 'validate'

post-comment:
  description: 'Post validation results as PR comment'
  required: false
  default: 'true'

comment-tag:
  description: 'Unique tag for updating the same comment'
  required: false
  default: 'releez-validate-release'
```

**Outputs**:

```yaml
release-version:
  description: 'The release version that will be created'
  value: ${{ steps.detect.outputs.version }}

project:
  description: 'Project name for monorepo releases'
  value: ${{ steps.detect.outputs.project }}

release-preview:
  description: 'Preview of changes and version'
  value: ${{ steps.preview.outputs.content }}

release-notes:
  description: 'Preview of release notes'
  value: ${{ steps.notes.outputs.content }}

validation-status:
  description: 'Validation status: success or failure'
  value: ${{ steps.validate.outputs.status }}
```

**Implementation Steps**:

```yaml
steps:
  # 1. Detect release from branch
  - name: Detect release information
    id: detect
    shell: bash
    run: |
      RELEASE_INFO=$(releez release detect-from-branch)
      echo "version=$(echo $RELEASE_INFO | jq -r '.version')" >> $GITHUB_OUTPUT
      echo "project=$(echo $RELEASE_INFO | jq -r '.project // ""')" >> $GITHUB_OUTPUT

  # 2. Run release preview (dry-run)
  - name: Preview release
    id: preview
    shell: bash
    run: |
      PROJECT_FLAG=""
      if [ -n "${{ steps.detect.outputs.project }}" ]; then
        PROJECT_FLAG="--project ${{ steps.detect.outputs.project }}"
      fi

      PREVIEW=$(releez release preview --dry-run $PROJECT_FLAG)

      {
        echo "content<<EOF"
        echo "$PREVIEW"
        echo "EOF"
      } >> $GITHUB_OUTPUT

  # 3. Generate release notes preview
  - name: Generate release notes
    id: notes
    shell: bash
    run: |
      PROJECT_FLAG=""
      if [ -n "${{ steps.detect.outputs.project }}" ]; then
        PROJECT_FLAG="--project ${{ steps.detect.outputs.project }}"
      fi

      NOTES=$(releez release notes $PROJECT_FLAG)

      {
        echo "content<<EOF"
        echo "$NOTES"
        echo "EOF"
      } >> $GITHUB_OUTPUT

  # 4. Mark validation status
  - name: Set validation status
    id: validate
    shell: bash
    run: echo "status=success" >> $GITHUB_OUTPUT

  # 5. Post PR comment (optional)
  - name: Comment on PR
    if: inputs.post-comment == 'true'
    uses: thollander/actions-comment-pull-request@v3
    with:
      comment-tag: ${{ inputs.comment-tag }}
      mode: recreate
      message: |
        ✅ Releez release validation completed successfully.

        # Releez: Release Preview

        ${{ steps.preview.outputs.content }}

        # Releez: Release Notes

        ${{ steps.notes.outputs.content }}
```

### Mode: `version-artifact`

**Purpose**: Compute artifact versions for builds (replaces
`releez-version-artifact-action`).

**Trigger**: Any workflow needing version computation

**Workflow**:

1. Optionally detect version from branch (if on release branch)
2. Compute artifact versions in requested formats
3. Return JSON arrays of versions

**Inputs**:

```yaml
mode:
  description: 'Action mode'
  required: true
  # Must be: 'version-artifact'

version-override:
  description: 'Explicit version to use (skips detection)'
  required: false
  default: ''

is-full-release:
  description: 'Whether this is a full release'
  required: false
  default: 'false'

prerelease-type:
  description: 'Prerelease type: alpha, beta, rc'
  required: false
  default: 'alpha'

prerelease-number:
  description: 'Prerelease number (e.g., PR number)'
  required: false
  default: ''

build-number:
  description: 'Build number (e.g., run number)'
  required: false
  default: '${{ github.run_number }}'

alias-versions:
  description: 'Alias version strategy for full releases'
  required: false
  default: 'none'

detect-from-branch:
  description: 'Auto-detect version from release branch'
  required: false
  default: 'false'
```

**Outputs**:

```yaml
# JSON outputs
semver-versions:
  description: 'JSON array of semver versions'
  value: ${{ fromJson(steps.compute.outputs.json).semver }}

docker-versions:
  description: 'JSON array of docker versions'
  value: ${{ fromJson(steps.compute.outputs.json).docker }}

pep440-versions:
  description: 'JSON array of PEP440 versions'
  value: ${{ fromJson(steps.compute.outputs.json).pep440 }}

# Single-value outputs (first in array)
semver-version:
  description: 'Primary semver version'
  value: ${{ fromJson(steps.compute.outputs.json).semver[0] }}

docker-version:
  description: 'Primary docker version'
  value: ${{ fromJson(steps.compute.outputs.json).docker[0] }}

pep440-version:
  description: 'Primary PEP440 version'
  value: ${{ fromJson(steps.compute.outputs.json).pep440[0] }}

# Metadata
detected-project:
  description: 'Detected project name (if detect-from-branch=true)'
  value: ${{ steps.detect.outputs.project }}
```

**Implementation Steps**:

```yaml
steps:
  # 1. Optionally detect from branch
  - name: Detect from branch
    id: detect
    if: inputs.detect-from-branch == 'true'
    shell: bash
    run: |
      RELEASE_INFO=$(releez release detect-from-branch)
      echo "version=$(echo $RELEASE_INFO | jq -r '.version')" >> $GITHUB_OUTPUT
      echo "project=$(echo $RELEASE_INFO | jq -r '.project // ""')" >> $GITHUB_OUTPUT
    continue-on-error: true

  # 2. Determine version to use
  - name: Determine version
    id: version
    shell: bash
    run: |
      if [ -n "${{ inputs.version-override }}" ]; then
        echo "value=${{ inputs.version-override }}" >> $GITHUB_OUTPUT
      elif [ -n "${{ steps.detect.outputs.version }}" ]; then
        echo "value=${{ steps.detect.outputs.version }}" >> $GITHUB_OUTPUT
      else
        # Use git-cliff to compute next version
        VERSION=$(releez version artifact --version-override "" | jq -r '.semver[0]')
        echo "value=$VERSION" >> $GITHUB_OUTPUT
      fi

  # 3. Compute artifact versions
  - name: Compute artifact versions
    id: compute
    shell: bash
    run: |
      PRERELEASE_FLAGS=""
      if [ "${{ inputs.is-full-release }}" != "true" ]; then
        PRERELEASE_FLAGS="--prerelease-type ${{ inputs.prerelease-type }}"
        if [ -n "${{ inputs.prerelease-number }}" ]; then
          PRERELEASE_FLAGS="$PRERELEASE_FLAGS --prerelease-number ${{ inputs.prerelease-number }}"
        fi
        if [ -n "${{ inputs.build-number }}" ]; then
          PRERELEASE_FLAGS="$PRERELEASE_FLAGS --build-number ${{ inputs.build-number }}"
        fi
      fi

      # Get unified JSON output (no --scheme)
      VERSIONS_JSON=$(releez version artifact \
        --version-override "${{ steps.version.outputs.value }}" \
        --is-full-release=${{ inputs.is-full-release }} \
        --alias-versions "${{ inputs.alias-versions }}" \
        $PRERELEASE_FLAGS)

      {
        echo "json<<EOF"
        echo "$VERSIONS_JSON"
        echo "EOF"
      } >> $GITHUB_OUTPUT
```

## Complete action.yml Structure

```yaml
name: 'Releez Action'
description: 'Unified GitHub Action for releez release automation'
author: 'hotdog-werx'

branding:
  icon: 'package'
  color: 'blue'

inputs:
  mode:
    description: |
      Action mode: finalize, validate, or version-artifact
      - finalize: Create tags and outputs after PR merge
      - validate: Validate release PR before merge
      - version-artifact: Compute artifact versions
    required: true

  # Common inputs
  version-override:
    description: 'Override version (skips auto-detection)'
    required: false
    default: ''

  is-full-release:
    description: 'Whether this is a full release (not prerelease)'
    required: false
    default: 'true'

  alias-versions:
    description: 'Alias version strategy: none, major, minor'
    required: false
    default: 'none'

  dry-run:
    description: 'Run without making changes (for testing)'
    required: false
    default: 'false'

  # Validate mode inputs
  post-comment:
    description: '[validate] Post validation results as PR comment'
    required: false
    default: 'true'

  comment-tag:
    description: '[validate] Unique tag for PR comment'
    required: false
    default: 'releez-validate-release'

  # Version-artifact mode inputs
  prerelease-type:
    description: '[version-artifact] Prerelease type: alpha, beta, rc'
    required: false
    default: 'alpha'

  prerelease-number:
    description: '[version-artifact] Prerelease number'
    required: false
    default: ''

  build-number:
    description: '[version-artifact] Build number'
    required: false
    default: '${{ github.run_number }}'

  detect-from-branch:
    description: '[version-artifact] Auto-detect version from release branch'
    required: false
    default: 'false'

outputs:
  # Version outputs
  release-version:
    description: 'The release version'
    value: ${{ steps.output.outputs.release-version }}

  project:
    description: 'Project name (monorepo only)'
    value: ${{ steps.output.outputs.project }}

  # Version arrays (JSON)
  semver-versions:
    description: 'JSON array of semver versions'
    value: ${{ steps.output.outputs.semver-versions }}

  docker-versions:
    description: 'JSON array of docker versions'
    value: ${{ steps.output.outputs.docker-versions }}

  pep440-versions:
    description: 'JSON array of PEP440 versions'
    value: ${{ steps.output.outputs.pep440-versions }}

  # Single versions (backwards compatibility)
  semver-version:
    description: 'Primary semver version'
    value: ${{ steps.output.outputs.semver-version }}

  docker-version:
    description: 'Primary docker version'
    value: ${{ steps.output.outputs.docker-version }}

  pep440-version:
    description: 'Primary PEP440 version'
    value: ${{ steps.output.outputs.pep440-version }}

  # Content outputs
  release-notes:
    description: 'Release notes markdown'
    value: ${{ steps.output.outputs.release-notes }}

  release-preview:
    description: '[validate] Release preview'
    value: ${{ steps.output.outputs.release-preview }}

  validation-status:
    description: '[validate] Validation status'
    value: ${{ steps.output.outputs.validation-status }}

runs:
  using: 'composite'
  steps:
    - name: Install mise tools
      uses: jdx/mise-action@v3
      shell: bash

    - name: Validate mode
      shell: bash
      run: |
        if [[ ! "${{ inputs.mode }}" =~ ^(finalize|validate|version-artifact)$ ]]; then
          echo "Error: Invalid mode '${{ inputs.mode }}'. Must be: finalize, validate, or version-artifact"
          exit 1
        fi

    - name: Run finalize mode
      id: finalize
      if: inputs.mode == 'finalize'
      shell: bash
      run: |
        # Implementation from "Mode: finalize" section above
        # ...

    - name: Run validate mode
      id: validate
      if: inputs.mode == 'validate'
      shell: bash
      run: |
        # Implementation from "Mode: validate" section above
        # ...

    - name: Run version-artifact mode
      id: version-artifact
      if: inputs.mode == 'version-artifact'
      shell: bash
      run: |
        # Implementation from "Mode: version-artifact" section above
        # ...

    - name: Set outputs
      id: output
      shell: bash
      run: |
        # Aggregate outputs from the appropriate mode step
        # ...
```

## Usage Examples

### Example 1: Validate Release PR (Single Repo)

```yaml
name: Validate Release

on:
  pull_request:
    types: [opened, reopened, synchronize, edited]

permissions:
  pull-requests: write
  contents: read

jobs:
  validate:
    if: startsWith(github.head_ref, 'release/')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: hotdog-werx/releez-action@v1
        with:
          mode: validate
          post-comment: true
```

### Example 2: Finalize Release (Single Repo)

```yaml
name: Finalize Release

on:
  pull_request:
    types: [closed]

permissions:
  contents: write

jobs:
  finalize:
    if: |
      github.event.pull_request.merged == true &&
      startsWith(github.event.pull_request.head.ref, 'release/')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: hotdog-werx/releez-action@v1
        id: releez
        with:
          mode: finalize
          is-full-release: true
          alias-versions: major

      - name: Build and publish
        run: |
          uv version ${{ steps.releez.outputs.pep440-version }} --frozen
          uv build
          uv publish dist/*
        env:
          UV_PUBLISH_TOKEN: ${{ secrets.PYPI_TOKEN }}

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          tag_name: ${{ steps.releez.outputs.release-version }}
          body: ${{ steps.releez.outputs.release-notes }}
```

### Example 3: Monorepo with Changed Projects Detection

```yaml
name: Build Changed Projects

on:
  pull_request:

jobs:
  detect:
    runs-on: ubuntu-latest
    outputs:
      matrix: ${{ steps.changed.outputs.matrix }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: jdx/mise-action@v3

      - name: Detect changed projects
        id: changed
        run: |
          CHANGED=$(releez projects changed --format json)
          echo "matrix=$(echo $CHANGED | jq -c '.include')" >> $GITHUB_OUTPUT

  build:
    needs: detect
    if: needs.detect.outputs.matrix != '[]'
    strategy:
      matrix: ${{ fromJson(needs.detect.outputs.matrix) }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: hotdog-werx/releez-action@v1
        id: version
        with:
          mode: version-artifact
          detect-from-branch: true
          prerelease-type: alpha
          prerelease-number: ${{ github.event.pull_request.number }}
          build-number: ${{ github.run_number }}

      - name: Build artifact
        run: |
          echo "Building ${{ matrix.project }} version ${{ steps.version.outputs.docker-version }}"
          # Build with detected version
```

### Example 4: Finalize Monorepo Release

```yaml
name: Finalize Monorepo Release

on:
  pull_request:
    types: [closed]

permissions:
  contents: write

jobs:
  finalize:
    if: |
      github.event.pull_request.merged == true &&
      startsWith(github.event.pull_request.head.ref, 'release/')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: hotdog-werx/releez-action@v1
        id: releez
        with:
          mode: finalize
          is-full-release: true
          alias-versions: major

      # Project is auto-detected from branch name (e.g., release/core-1.2.3)
      - name: Build and publish project
        if: steps.releez.outputs.project != ''
        run: |
          PROJECT="${{ steps.releez.outputs.project }}"
          VERSION="${{ steps.releez.outputs.pep440-version }}"

          cd "packages/$PROJECT"
          uv version "$VERSION" --frozen
          uv build
          uv publish dist/*
        env:
          UV_PUBLISH_TOKEN: ${{ secrets.PYPI_TOKEN }}

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          tag_name: ${{ steps.releez.outputs.release-version }}
          body: ${{ steps.releez.outputs.release-notes }}
```

## Implementation Checklist

- [ ] Create `hotdog-werx/releez-action` repository
- [ ] Implement `action.yml` with composite run steps
- [ ] Add mode validation logic
- [ ] Implement finalize mode
- [ ] Implement validate mode
- [ ] Implement version-artifact mode
- [ ] Add comprehensive examples in README
- [ ] Test with single-repo workflow
- [ ] Test with monorepo workflow
- [ ] Document migration from old actions
- [ ] Create v1 release

## Migration Guide (for users)

### From `releez-finalize-action@v0`

**Before**:

```yaml
- uses: hotdog-werx/releez-finalize-action@v0
  with:
    is-full-release: 'true'
```

**After**:

```yaml
- uses: hotdog-werx/releez-action@v1
  with:
    mode: finalize
    is-full-release: true
```

### From `releez-version-artifact-action`

**Before**:

```yaml
- uses: hotdog-werx/releez-version-artifact-action@v0
  with:
    scheme: docker
    prerelease-number: ${{ github.event.pull_request.number }}
```

**After**:

```yaml
- uses: hotdog-werx/releez-action@v1
  id: version
  with:
    mode: version-artifact
    prerelease-number: ${{ github.event.pull_request.number }}

# Access specific version format:
# ${{ steps.version.outputs.docker-version }}
# Or all versions: ${{ steps.version.outputs.docker-versions }}
```

## Technical Notes

### Branch Name Parsing Safety

The action uses `releez release detect-from-branch` internally, which:

- Only accepts branches starting with `release/`
- Validates against configured monorepo projects
- Returns structured JSON (no string parsing vulnerabilities)
- Controlled by releez (not user input)

### JSON Output Structure

All version outputs use JSON arrays for consistency:

```json
{
  "semver": ["1.2.3", "v1"],
  "docker": ["1.2.3", "v1"],
  "pep440": ["1.2.3"]
}
```

Access in workflows:

```yaml
# Single value (first in array)
${{ steps.releez.outputs.semver-version }}

# All values (JSON array)
${{ steps.releez.outputs.semver-versions }}

# Iterate over versions
${{ fromJson(steps.releez.outputs.semver-versions) }}
```

### Error Handling

All modes should:

1. Validate inputs early
2. Provide clear error messages
3. Exit with code 1 on failure
4. Log detailed information for debugging

### Testing Strategy

1. **Unit tests**: Test each mode independently
2. **Integration tests**: Full workflows in test repository
3. **Monorepo tests**: Multi-project scenarios
4. **Edge cases**: Invalid branches, missing config, etc.
