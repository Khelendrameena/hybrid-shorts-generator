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

CUDA libraries (cuBLAS + cuDNN) pip se lagana sabse halka tareeqa hai —
koi 4 GB ka apt toolkit nahi chahiye. Project ke venv me bas ye chalao:

```bash
cd ~/video/hybrid-shorts-generator   # (tumhara path) aur .venv active rakho
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
```

Code in dono packages ko khud dhoondh ke load karta hai
(`whisper_engine._cuda_usable` → pip libs preload), aur `run.sh` unhe
`LD_LIBRARY_PATH` me bhi daal deta hai. Uske baad project restart karo
(`Ctrl+C`, `./run.sh`) — agli transcription ke job message me device
**cuda** dikhega aur Whisper GPU par chalega.

Note (2026-11-11 ko verify hua): apt wala tareeqa aadha hi kaam karta hai —
`cuda-toolkit-12-6` NVIDIA ke wsl-ubuntu repo me hai, lekin
`libcudnn9-cuda-12` us repo me **nahi** milta ("Unable to locate package"),
aur ek package na milne par apt poora install rok deta hai. Isliye cuDNN
ke liye pip wala rasta hi sahi hai; toolkit chahiye hi ho to sirf
`apt-get install -y cuda-toolkit-12-6` chalana, saath me koi cudnn package
mat jodna. Aur pura `cuda` metapackage kabhi mat lagana — wo Linux display
driver lata hai jo WSL me conflict karta hai.

**Meri recommendation:** permanent ke liye Option B kar do. Colab tab
kaam ka hai jab laptop band ho ya kahin aur se kaam karna ho.
