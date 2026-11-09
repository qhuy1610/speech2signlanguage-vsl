import json, re, unicodedata, torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

# ====== SỬA 2 DÒNG NÀY ======
MODEL_DIR = "./best_model_export"        # máy local vd: "./best_model"
VOCAB     = "./results_bundle/processed_data/gloss_vocab.json"  # máy local vd: "./gloss_vocab.json"
# ============================
PREFIX, MAX_LEN = "dịch sang gloss: ", 128   # phải đúng như lúc train

tok   = AutoTokenizer.from_pretrained(MODEL_DIR)
dev   = "cuda" if torch.cuda.is_available() else "cpu"
model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_DIR).to(dev).eval()
CANON = json.load(open(f"{MODEL_DIR}/canon_map.json", encoding="utf-8"))
ALL_SIGNS = set(json.load(open(VOCAB, encoding="utf-8")))

nfc = lambda s: re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(s))).strip()
canon_tok = lambda t: CANON.get(t, t.replace("_", " "))

def predict_json(sentences, num_beams=4):
    if isinstance(sentences, str): sentences = [sentences]
    clean = [nfc(nfc(x).lower()) for x in sentences]      # train không có chữ hoa
    inp = tok([PREFIX + c for c in clean], return_tensors="pt", padding=True,
              truncation=True, max_length=MAX_LEN).to(dev)
    with torch.no_grad():
        o = model.generate(**inp, num_beams=num_beams, max_length=MAX_LEN)
    glosses = [[canon_tok(t) for t in d.split()]
               for d in tok.batch_decode(o, skip_special_tokens=True)]
    return [{"text": t, "Gloss": g, "unknown_signs": [x for x in g if x not in ALL_SIGNS]}
            for t, g in zip(clean, glosses)]
