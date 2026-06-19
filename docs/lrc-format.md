# LRC and WLRC Formats

## LRC (Phrase-level)
LRC is the standard format for synchronized lyrics.
Each line begins with a timestamp `[mm:ss.xx]` followed by the lyric text.

```lrc
[00:12.34] This is the first line
[00:15.67] This is the second line
```

## WLRC (Word-level)
WLRC is a proprietary word-level extension where each word has its own timestamp. This tool's `process` command can generate WLRC to allow words to light up incrementally.
```wlrc
[00:12.34] <00:12.34> This <00:12.80> is <00:13.10> a <00:13.50> word
```
