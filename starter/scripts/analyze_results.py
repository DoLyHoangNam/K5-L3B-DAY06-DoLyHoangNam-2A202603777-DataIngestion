"""Inspect retrieval traces, metadata compliance, and prepare audit samples."""
import json
from pathlib import Path


def main() -> None:
    project_root = Path(__file__).resolve().parents[2]
    results_dir = project_root / "results"
    manifest = json.loads((project_root / "data" / "manifest.json").read_text(encoding="utf-8"))

    valid_meta = {}
    for doc in manifest["documents"]:
        for p in doc["pages"]:
            valid_meta[(doc["source_id"], p["page"])] = (
                doc["local_path"],
                doc["year"],
                p["section"],
            )

    traces = {}
    for s in ["A", "B", "C"]:
        lines = (results_dir / f"traces_{s}.jsonl").read_text(encoding="utf-8").splitlines()
        traces[s] = [json.loads(line) for line in lines if line.strip()]

    print("=== PER-QUESTION HIT@1 / HIT@3 ===")
    for a, b, c in zip(traces["A"], traces["B"], traces["C"]):
        flt = str(a["question_filter"])
        print(
            f"{a['question_id']} ({a['split']:4s}, {a['type']:18s}, flt={flt:40s}) | "
            f"A:{int(a['hit_at_1'])}/{int(a['hit_at_3'])} "
            f"B:{int(b['hit_at_1'])}/{int(b['hit_at_3'])} "
            f"C:{int(c['hit_at_1'])}/{int(c['hit_at_3'])}"
        )

    print("\n=== METADATA & FILTER COMPLIANCE ON TEST (q16..q20) ===")
    for s in ["A", "B", "C"]:
        ok, total = 0, 0
        flt_ok, flt_total = 0, 0
        for t in traces[s]:
            if t["split"] != "test":
                continue
            for h in t["top_k"]:
                total += 1
                key = (h["document_id"], h["page"])
                if key in valid_meta:
                    exp_src, exp_yr, exp_sec = valid_meta[key]
                    if h["source"] == exp_src and h["year"] == exp_yr and h["section"] == exp_sec:
                        ok += 1
            if t["applied_filter"]:
                flt_total += 1
                if all(all(h.get(k) == v for k, v in t["applied_filter"].items()) for h in t["top_k"]):
                    flt_ok += 1
        flt_str = f"{flt_ok}/{flt_total}" if flt_total else "N/A"
        print(f"Strategy {s}: test_metadata_ok={ok}/{total} | test_filter_ok={flt_str}")

    print("\n=== ALL FILTER QUESTIONS: B vs C ===")
    for idx in range(len(traces["B"])):
        b, c = traces["B"][idx], traces["C"][idx]
        if b["question_filter"]:
            print(f"\n[{b['question_id']}] ({b['split']}) filter={b['question_filter']}")
            print(f"  Q: {b['question']}")
            print("  B top3:", [(h["document_id"], h["page"], h["year"], h["section"], h["matched_gold"], h["similarity"]) for h in b["top_k"]])
            print("  C top3:", [(h["document_id"], h["page"], h["year"], h["section"], h["matched_gold"], h["similarity"]) for h in c["top_k"]])

    print("\n=== TEST QUESTIONS DETAIL (q16..q20) FOR GROUNDING AUDIT ===")
    for idx in range(len(traces["A"])):
        if traces["A"][idx]["split"] != "test":
            continue
        q = traces["A"][idx]
        print(f"\n--- {q['question_id']}: {q['question']} ---")
        print(f"Expected: {q['expected_answer']} | Gold: {q['gold_source_id']} p.{q['gold_page']}")
        for s in ["A", "B", "C"]:
            t = traces[s][idx]
            print(f"  [{s}] hit1={t['hit_at_1']} hit3={t['hit_at_3']}")
            for h in t["top_k"]:
                snippet = " ".join(h["text"].split())[:220]
                print(f"    #{h['rank']} ({h['document_id']} p.{h['page']}, sim={h['similarity']}, gold={h['matched_gold']}): {snippet}...")


if __name__ == "__main__":
    main()
