# Configuration

You can provide a `config.yaml` file and pass it via `--config path/to/config.yaml`.

## Example
```yaml
puller:
  search_threads: 5
  download_threads: 5
  overwrite: false
  preserve_structure: true

processor:
  max_phrase_duration: 2.5
  min_phrase_duration: 0.3
  max_words_per_phrase: 8
  use_onset_detection: false
```
