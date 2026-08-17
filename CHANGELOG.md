## [1.0.5] - 2026-08-17

### 🐛 Bug Fixes

- Fix action logic when in monorepo mode the app name and prefix vary (#68) by
  [@jamestrousdale](https://github.com/jamestrousdale) in
  [#68](https://github.com/hotdog-werx/releez/pull/68)

## [1.0.4] - 2026-08-14

### 🐛 Bug Fixes

- Action is read-only to uv cache (#66) by
  [@jamestrousdale](https://github.com/jamestrousdale) in
  [#66](https://github.com/hotdog-werx/releez/pull/66)

## [1.0.3] - 2026-08-13

### 🐛 Bug Fixes

- Bump sticky pull request action version (#64) by
  [@jamestrousdale](https://github.com/jamestrousdale) in
  [#64](https://github.com/hotdog-werx/releez/pull/64)

## [1.0.2] - 2026-08-09

### 🐛 Bug Fixes

- Version override doesn't require prefix (#60) by
  [@jamestrousdale](https://github.com/jamestrousdale) in
  [#60](https://github.com/hotdog-werx/releez/pull/60)

### ⚙️ Miscellaneous Tasks

- Use devkit (#62) by [@jamestrousdale](https://github.com/jamestrousdale) in
  [#62](https://github.com/hotdog-werx/releez/pull/62)

## [1.0.1] - 2026-05-27

### 🐛 Bug Fixes

- Fix doctor changelog check in monorepo mode (#57) by
  [@jamestrousdale](https://github.com/jamestrousdale) in
  [#57](https://github.com/hotdog-werx/releez/pull/57)

- Add logging when git cliff fails (#56) by
  [@jamestrousdale](https://github.com/jamestrousdale) in
  [#56](https://github.com/hotdog-werx/releez/pull/56)

## [1.0.0] - 2026-05-19

### 🚀 Features

- Validate commit message + validate-pr-title action mode (#36) by
  [@jamestrousdale](https://github.com/jamestrousdale) in
  [#36](https://github.com/hotdog-werx/releez/pull/36)

- _(release)_ Add maintenance branch support and confirmation (#37) by
  [@jamestrousdale](https://github.com/jamestrousdale) in
  [#37](https://github.com/hotdog-werx/releez/pull/37)

- Get rid of typer (#47) by [@jamestrousdale](https://github.com/jamestrousdale)
  in [#47](https://github.com/hotdog-werx/releez/pull/47)

- _(cli)_ Releez doctor command (#48) by
  [@jamestrousdale](https://github.com/jamestrousdale) in
  [#48](https://github.com/hotdog-werx/releez/pull/48)

- Use marocchino/sticky-pull-request-comment (#50) by
  [@jamestrousdale](https://github.com/jamestrousdale) in
  [#50](https://github.com/hotdog-werx/releez/pull/50)

### 🐛 Bug Fixes

- Refactor CLI functions (#42) by
  [@jamestrousdale](https://github.com/jamestrousdale) in
  [#42](https://github.com/hotdog-werx/releez/pull/42)

- Remove all deprecated code (#43) by
  [@jamestrousdale](https://github.com/jamestrousdale) in
  [#43](https://github.com/hotdog-werx/releez/pull/43)

- Force pull tags to handle alias tags out of sync (#44) by
  [@jamestrousdale](https://github.com/jamestrousdale) in
  [#44](https://github.com/hotdog-werx/releez/pull/44)

- Enable singular output versions from action (#46) by
  [@jamestrousdale](https://github.com/jamestrousdale) in
  [#46](https://github.com/hotdog-werx/releez/pull/46)

- Action needs github token by
  [@jamestrousdale](https://github.com/jamestrousdale)

### ⚙️ Miscellaneous Tasks

- Add some additional test documentation by
  [@jamestrousdale](https://github.com/jamestrousdale)

- Rename classes with leading underscores by
  [@jamestrousdale](https://github.com/jamestrousdale)

## [0.3.4] - 2026-03-04

### 🐛 Bug Fixes

- Make releez.toml config paths the same as pyproject (#33) by
  [@jamestrousdale](https://github.com/jamestrousdale) in
  [#33](https://github.com/hotdog-werx/releez/pull/33)

## [0.3.3] - 2026-03-03

### 🐛 Bug Fixes

- _(action)_ Make sure action doesn't clobber alias-versions setting (#31) by
  [@jamestrousdale](https://github.com/jamestrousdale) in
  [#31](https://github.com/hotdog-werx/releez/pull/31)

## [0.3.2] - 2026-03-03

### 🐛 Bug Fixes

- _(ci)_ Major alias tag for action support by
  [@jamestrousdale](https://github.com/jamestrousdale)

## [0.3.1] - 2026-03-03

### 🐛 Bug Fixes

- _(action)_ Generate release notes before tagging (#28) by
  [@jamestrousdale](https://github.com/jamestrousdale) in
  [#28](https://github.com/hotdog-werx/releez/pull/28)

## [0.3.0] - 2026-03-02

### 🚀 Features

- Post changelog hooks (#22) by
  [@jamestrousdale](https://github.com/jamestrousdale) in
  [#22](https://github.com/hotdog-werx/releez/pull/22)

- Monorepo support with independent project versioning (#23) by
  [@jamestrousdale](https://github.com/jamestrousdale) in
  [#23](https://github.com/hotdog-werx/releez/pull/23)

- Add documentation site (#24) by
  [@jamestrousdale](https://github.com/jamestrousdale) in
  [#24](https://github.com/hotdog-werx/releez/pull/24)

### 🐛 Bug Fixes

- Bump typer to 0.24.1 by [@jamestrousdale](https://github.com/jamestrousdale)

- _(ci)_ Fix permissions on docs deploy job by
  [@jamestrousdale](https://github.com/jamestrousdale)

### ⚙️ Miscellaneous Tasks

- _(docs)_ Link to GitHub pages docs by
  [@jamestrousdale](https://github.com/jamestrousdale)

## [0.2.6] - 2026-02-18

### 🐛 Bug Fixes

- Implement --version option and export **version** const (#20) by
  [@jamestrousdale](https://github.com/jamestrousdale) in
  [#20](https://github.com/hotdog-werx/releez/pull/20)

## [0.2.5] - 2026-02-04

### ⚙️ Miscellaneous Tasks

- Add codecov (#18) by [@jamestrousdale](https://github.com/jamestrousdale) in
  [#18](https://github.com/hotdog-werx/releez/pull/18)

## [0.2.4] - 2026-02-04

### ⚙️ Miscellaneous Tasks

- Fix project classifiers by
  [@jamestrousdale](https://github.com/jamestrousdale)

## [0.2.3] - 2026-02-04

### ⚙️ Miscellaneous Tasks

- Add license, metadata, etc by
  [@jamestrousdale](https://github.com/jamestrousdale)

## [0.2.2] - 2026-02-03

### ⚙️ Miscellaneous Tasks

- Publish to prod pypi by [@jamestrousdale](https://github.com/jamestrousdale)

## [0.2.1] - 2026-02-03

### ⚙️ Miscellaneous Tasks

- Add publish to finalize workflow by
  [@jamestrousdale](https://github.com/jamestrousdale)

## [0.2.0] - 2026-01-31

### 🚀 Features

- _(cli)_ Add changelog regenerate command (#7) by
  [@jmlopez-rod](https://github.com/jmlopez-rod) in
  [#7](https://github.com/hotdog-werx/releez/pull/7)

## [0.1.3] - 2026-01-08

### 🐛 Bug Fixes

- Update alias versions handling (#5) by
  [@jamestrousdale](https://github.com/jamestrousdale) in
  [#5](https://github.com/hotdog-werx/releez/pull/5)

### ⚙️ Miscellaneous Tasks

- _(docs)_ Update documentation by
  [@jamestrousdale](https://github.com/jamestrousdale)

## [0.1.2] - 2026-01-06

### 🐛 Bug Fixes

- Allow RELEEZ_GITHUB_TOKEN alias by
  [@jamestrousdale](https://github.com/jamestrousdale)

## [0.1.1] - 2026-01-06

### 🚜 Refactor

- Rename alias_tags to alias_versions and update related logic by
  [@jamestrousdale](https://github.com/jamestrousdale)

## [0.1.0] - 2026-01-01

### 🚀 Features

- Initial implementation from prototype (#1) by
  [@jamestrousdale](https://github.com/jamestrousdale) in
  [#1](https://github.com/hotdog-werx/releez/pull/1)

### 🐛 Bug Fixes

- Fix tag filter by [@jamestrousdale](https://github.com/jamestrousdale)

- Use tag pattern instead of skip tags by
  [@jamestrousdale](https://github.com/jamestrousdale)

- Ignore alias tags for pep440 by
  [@jamestrousdale](https://github.com/jamestrousdale)

- _(settings)_ Support kebab-case keys in config files by
  [@jamestrousdale](https://github.com/jamestrousdale)

- _(settings)_ Enhance alias handling for kebab-case and snake_case keys by
  [@jamestrousdale](https://github.com/jamestrousdale)

### ⚙️ Miscellaneous Tasks

- Initial commit by [@jamestrousdale](https://github.com/jamestrousdale)

- Initial repo setup by [@jamestrousdale](https://github.com/jamestrousdale)

- Default scheme is semver by
  [@jamestrousdale](https://github.com/jamestrousdale)

- _(ci)_ Add release workflows by
  [@jamestrousdale](https://github.com/jamestrousdale)

- _(ci)_ Dprint format by [@jamestrousdale](https://github.com/jamestrousdale)

- _(ci)_ Add start release workflow by
  [@jamestrousdale](https://github.com/jamestrousdale)

- _(ci)_ Fix hooks by [@jamestrousdale](https://github.com/jamestrousdale)

- Set up for release by [@jamestrousdale](https://github.com/jamestrousdale)
