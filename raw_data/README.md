# Populating the Data folder

From within this folder, run
```bash
curl -L https://github.com/cltk/grc_text_perseus/archive/a1628ed.tar.gz | tar -xz --strip=1 --wildcards "*json/*.json" -C cltk_json
mv json/herodotus__histories.json cltk_json/herodotus__the-histories__grc.json
mv "cltk_json/lysias__against-agoratus-in-pursuance-of-a-writ__grc.json" "cltk_json/lysias__against-agoratus-in-pursuance-of-a-writ__eng.json"
mv "cltk_json/lysias__against-andocides-for-impiety__grc.json" "cltk_json/lysias__against-andocides-for-impiety__eng.json"
rm -rf json
```

or just run `download_grc_json.sh`
