import time, string, json, urllib.request, urllib.error
import numpy as np

SUPABASE_URL = "https://vbycdjhdyxswqosefbro.supabase.co"
SUPABASE_KEY = "sb_publishable_lWZ36Wnvmm_dRG-NPw8a7Q_5ofPjgZR"

CHUNK = 20000
CORPUS_FILE = "complete_shakespeare.txt"
LOG_FILE = "results.txt"

letters = string.ascii_lowercase
letters_np = np.frombuffer(letters.encode(), dtype=np.uint8)


def get_corpus(path):
    f = open(path, "r", encoding="utf-8")
    text = f.read()
    f.close()
    out = []
    for ch in text:
        if ch.isalpha():
            out.append(ch.lower())
    return "".join(out)


def push_to_db(table, row):
    try:
        req = urllib.request.Request(
            SUPABASE_URL + "/rest/v1/" + table,
            data=json.dumps(row).encode(),
            method="POST",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": "Bearer " + SUPABASE_KEY,
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
        )
        urllib.request.urlopen(req, timeout=5).close()
    except Exception as e:
        print("  (db push failed:", e, ")")



class SAM:
    def __init__(self, s):
        self.link = [-1]
        self.len = [0]
        self.to = [{}]
        self.last = 0
        for c in s:
            self.add(c)

    def add(self, c):
        cur = len(self.len)
        self.len.append(self.len[self.last] + 1)
        self.link.append(-1)
        self.to.append({})
        p = self.last
        while p != -1 and c not in self.to[p]:
            self.to[p][c] = cur
            p = self.link[p]
        if p == -1:
            self.link[cur] = 0
        else:
            q = self.to[p][c]
            if self.len[p] + 1 == self.len[q]:
                self.link[cur] = q
            else:
                clone = len(self.len)
                self.len.append(self.len[p] + 1)
                self.link.append(self.link[q])
                self.to.append(dict(self.to[q]))
                while p != -1 and self.to[p].get(c) == q:
                    self.to[p][c] = clone
                    p = self.link[p]
                self.link[q] = clone
                self.link[cur] = clone
        self.last = cur


def main():
    print("loading shakespeare from", CORPUS_FILE)
    corpus = get_corpus(CORPUS_FILE)
    print(f"{len(corpus):,} letters total (punctuation/spaces stripped)")
    print("building the automaton...")
    sam = SAM(corpus)
    print("ok, starting\n")

    to, link, ln = sam.to, sam.link, sam.len

    log = open(LOG_FILE, "a", buffering=1, encoding="utf-8")
    log.write("\n--- run started " + time.strftime("%Y-%m-%d %H:%M:%S") + " ---\n")

    cap = len(corpus) + 2048
    buf = []
    v = 0
    cur_len = 0
    best = 0
    best_str = ""

    total = 0
    t0 = time.time()
    last_print = t0

    try:
        while True:
            chunk = np.random.choice(letters_np, size=CHUNK).tobytes().decode()

            for c in chunk:
                while v != 0 and c not in to[v]:
                    v = link[v]
                    cur_len = ln[v]
                if c in to[v]:
                    v = to[v][c]
                    cur_len += 1
                else:
                    v = 0
                    cur_len = 0

                buf.append(c)
                total += 1

                if cur_len > best:
                    best = cur_len
                    best_str = "".join(buf[-best:])
                    elapsed = time.time() - t0
                    print(f"[{elapsed:.1f}s | {total:,} letters] new record: {best} -> {best_str!r}")
                    log.write(f"[{elapsed:.1f}s | {total} letters] length={best} match={best_str}\n")
                    push_to_db("monkey_matches", {
                        "matched_text": best_str,
                        "match_length": best,
                        "total_letters_at_match": total,
                        "elapsed_seconds": elapsed,
                    })

            if len(buf) > cap * 2:
                buf = buf[-cap:]

            if time.time() - last_print >= 2.0:
                elapsed = time.time() - t0
                rate = total / elapsed * 60
                print(f"  ...{elapsed:.1f}s | {rate:,.0f} letters/min | best so far: {best}")
                last_print = time.time()

    except KeyboardInterrupt:
        pass

    elapsed = time.time() - t0
    print("\n" + "=" * 60)
    print("stopped")
    print(f"ran for {elapsed:.1f}s, {total:,} letters, {total/elapsed*60:,.0f}/min avg" if elapsed > 0 else "ran for 0s")

    log.write(f"Total characters generated: {total}\n")
    log.write("--- run stopped " + time.strftime("%Y-%m-%d %H:%M:%S") + f" after {elapsed:.1f}s ---\n")
    log.close()

    push_to_db("monkey_runs", {
        "total_letters": total,
        "total_seconds": elapsed,
        "best_match_length": best or None,
        "best_match_text": best_str or None,
    })

    print("\nbest match found:")
    if best == 0:
        print("none, unlucky")
        return

    pos = corpus.find(best_str)
    print(f"{best} letters -> {best_str}")
    start = max(0, pos - 20)
    end = min(len(corpus), pos + best + 20)
    print("context:", "..." + corpus[start:end] + "...")


if __name__ == "__main__":
    main()
