# Fast chalane ke 2 tareeqe — Cloud GPU (Colab) ya apna GPU (WSL fix)

Project slow isliye hai kyunki WSL me Whisper **CPU** par chal raha hai —
WSL ke andar CUDA libraries (cuBLAS/cuDNN) installed nahi hain, isliye code
GPU dekh kar bhi use nahi kar pata. Do fix hain:

---

## Option A — Google Colab (cloud GPU, turant shuru)

Colab ka koi official CLI nahi hota — Colab browser me notebook se chalta
hai, aur login tumhara Google account lagega. Isliye repo me ready notebook
hai: **`colab.ipynb`** — bas kholo aur Run All dabao.

1. Ye link kholo:
   https://colab.research.google.com/github/Khelendrameena/hybrid-shorts-generator/blob/main/colab.ipynb
2. Runtime type **T4 GPU** select karo (Runtime → Change runtime type).
3. **Runtime → Run all**. Pehli baar ~8–12 min setup (packages + models).
4. Aakhri cell me **APP LINK** milega (trycloudflare URL) — wahi app hai.

Colab par kya fast hoga:
- Whisper → T4 GPU (CPU ke mukable kai guna fast)
- Laya → GPU
- Ollama qwen3:4b → GPU (VRAM 15 GB, aaram se)
- YouTube captions wali videos par transcript waise hi seconds me aata hai

Colab ki limits (honest):
- Session max ~12 ghante, kabhi pehle bhi band ho sakta hai (free tier)
- Session band = data delete. **Renders bante hi Export se ZIP download
  kar lo.** Notebook ki Step 2 wali Drive cell chala lo to projects
  Drive me save hote rahenge
- Har naye session me setup dobara (~8–12 min)

## Option B — Apna RTX 3050 hi fix kar do (permanent, recommended)

Ek baar WSL me CUDA toolkit + cuDNN laga do, phir hamesha ke liye tumhara
apna GPU chalega — koi session limit nahi, koi dobara setup nahi.
WSL Ubuntu terminal me (root ho tum):

```bash
wget https://developer.download.nvidia.com/compute/cuda/repos/wsl-ubuntu/x86_64/cuda-keyring_1.1-1_all.deb
dpkg -i cuda-keyring_1.1-1_all.deb
apt-get update
apt-get install -y cuda-toolkit-12-6 libcudnn9-cuda-12
ldconfig
ldconfig -p | grep -E "cublas.so.12|cudnn.so.9"   # dono dikhne chahiye
```

Dhyaan do:
- Sirf `cuda-toolkit` install karna — pura `cuda` package **mat** karna,
  wo Linux display driver bhi lata hai jo WSL me conflict karta hai
  (WSL Windows wala driver hi use karta hai).
- Download ~4 GB hai, ek baar ka kaam hai.
- Uske baad project restart karo (`Ctrl+C`, `./run.sh`) — agli
  transcription me job message me device **cuda** dikhega aur Whisper
  GPU par chalega. WSL wala download slow hai to raat ko laga ke chhod do.

**Meri recommendation:** permanent ke liye Option B kar do. Colab tab
kaam ka hai jab laptop band ho ya kahin aur se kaam karna ho.
