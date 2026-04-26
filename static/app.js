const state = {
  modules: [],
  currentModule: null,
  words: [],
  index: 0,
  quiz: [],
  quizIndex: 0,
  score: 0,
  quizMode: "module",
  isSubmittingQuizAnswer: false,
};

const els = {
  moduleList: document.querySelector("#moduleList"),
  finalQuizBtn: document.querySelector("#finalQuizBtn"),
  modeLabel: document.querySelector("#modeLabel"),
  moduleTitle: document.querySelector("#moduleTitle"),
  progressText: document.querySelector("#progressText"),
  progressBar: document.querySelector("#progressBar"),
  studyView: document.querySelector("#studyView"),
  quizView: document.querySelector("#quizView"),
  partOfSpeech: document.querySelector("#partOfSpeech"),
  wordCounter: document.querySelector("#wordCounter"),
  koreanWord: document.querySelector("#koreanWord"),
  romanization: document.querySelector("#romanization"),
  englishMeaning: document.querySelector("#englishMeaning"),
  exampleKo: document.querySelector("#exampleKo"),
  exampleEn: document.querySelector("#exampleEn"),
  traceGuide: document.querySelector("#traceGuide"),
  traceCanvas: document.querySelector("#traceCanvas"),
  clearTraceBtn: document.querySelector("#clearTraceBtn"),
  youtubeLink: document.querySelector("#youtubeLink"),
  videoSlot: document.querySelector("#videoSlot"),
  videoMeta: document.querySelector("#videoMeta"),
  prevBtn: document.querySelector("#prevBtn"),
  nextBtn: document.querySelector("#nextBtn"),
  startQuizBtn: document.querySelector("#startQuizBtn"),
  quizTitle: document.querySelector("#quizTitle"),
  scoreBox: document.querySelector("#scoreBox"),
  quizQuestion: document.querySelector("#quizQuestion"),
  quizOptions: document.querySelector("#quizOptions"),
  typedAnswer: document.querySelector("#typedAnswer"),
  submitTypedBtn: document.querySelector("#submitTypedBtn"),
  quizFeedback: document.querySelector("#quizFeedback"),
};

const trace = {
  drawing: false,
  ctx: null,
};

function normalize(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^\w\s]/g, "")
    .trim();
}

function youtubeEmbedUrl(url) {
  if (!url) return "";
  const match = url.match(/[?&]v=([^&]+)/);
  return match ? `https://www.youtube.com/embed/${match[1]}` : "";
}

async function getJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Request failed: ${url}`);
  }
  return response.json();
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    let message = `Request failed: ${url}`;
    try {
      const data = await response.json();
      message = data.detail || data.error || message;
    } catch {
      // ignore json parse failure
    }
    throw new Error(message);
  }

  return response.json();
}

function setFeedback(element, message, kind = "") {
  element.textContent = message;
  element.className = `feedback ${kind}`.trim();
}

function setRichQuizFeedback(data) {
  const lines = [];

  if (data.short_feedback) lines.push(data.short_feedback);
  if (data.why_wrong) lines.push(`Why: ${data.why_wrong}`);
  if (data.memory_tip) lines.push(`Tip: ${data.memory_tip}`);
  if (data.practice_reminder) lines.push(`Practice: ${data.practice_reminder}`);
  if (data.error) lines.push(`Debug: ${data.error}`);

  els.quizFeedback.textContent = lines.join(" ");
  els.quizFeedback.className = `feedback ${data.is_correct ? "good" : "bad"}`.trim();
}

function resizeTraceCanvas() {
  const canvas = els.traceCanvas;
  const rect = canvas.getBoundingClientRect();
  const scale = window.devicePixelRatio || 1;

  canvas.width = Math.max(1, Math.floor(rect.width * scale));
  canvas.height = Math.max(1, Math.floor(rect.height * scale));

  trace.ctx = canvas.getContext("2d");
  trace.ctx.setTransform(1, 0, 0, 1, 0, 0);
  trace.ctx.scale(scale, scale);
  trace.ctx.lineWidth = 8;
  trace.ctx.lineCap = "round";
  trace.ctx.lineJoin = "round";
  trace.ctx.strokeStyle = "#006d77";
}

function clearTraceCanvas() {
  if (!trace.ctx) resizeTraceCanvas();
  const rect = els.traceCanvas.getBoundingClientRect();
  trace.ctx.clearRect(0, 0, rect.width, rect.height);
}

function tracePoint(event) {
  const rect = els.traceCanvas.getBoundingClientRect();
  const point = event.touches ? event.touches[0] : event;
  return {
    x: point.clientX - rect.left,
    y: point.clientY - rect.top,
  };
}

function startTrace(event) {
  event.preventDefault();
  if (!trace.ctx) resizeTraceCanvas();
  trace.drawing = true;
  const point = tracePoint(event);
  trace.ctx.beginPath();
  trace.ctx.moveTo(point.x, point.y);
}

function moveTrace(event) {
  if (!trace.drawing) return;
  event.preventDefault();
  const point = tracePoint(event);
  trace.ctx.lineTo(point.x, point.y);
  trace.ctx.stroke();
}

function endTrace() {
  trace.drawing = false;
}

function renderModules() {
  els.moduleList.innerHTML = "";

  state.modules.forEach((module) => {
    const button = document.createElement("button");
    button.className = "module-button";

    if (state.currentModule && state.currentModule.module === module.module) {
      button.classList.add("active");
    }

    button.type = "button";
    button.innerHTML = `<strong>Module ${module.module}</strong><span>${module.module_name}</span>`;
    button.addEventListener("click", () => loadModule(module.module));
    els.moduleList.appendChild(button);
  });
}

function showStudy() {
  els.studyView.classList.remove("hidden");
  els.quizView.classList.add("hidden");
  els.prevBtn.classList.remove("hidden");
  els.nextBtn.classList.remove("hidden");
  els.startQuizBtn.classList.remove("hidden");
}

function showQuiz() {
  els.studyView.classList.add("hidden");
  els.quizView.classList.remove("hidden");
  els.prevBtn.classList.add("hidden");
  els.nextBtn.classList.add("hidden");
  els.startQuizBtn.classList.add("hidden");
}

function renderWord() {
  const word = state.words[state.index];
  if (!word) return;

  showStudy();
  els.modeLabel.textContent = "Study";
  els.moduleTitle.textContent = `Module ${state.currentModule.module}: ${state.currentModule.module_name}`;
  els.progressText.textContent = `${state.index + 1} / ${state.words.length}`;
  els.progressBar.style.width = `${((state.index + 1) / state.words.length) * 100}%`;
  els.partOfSpeech.textContent = word.part_of_speech || "word";
  els.wordCounter.textContent = `Word ${state.index + 1}`;
  els.koreanWord.textContent = word.korean;
  els.romanization.textContent = word.romanization;
  els.englishMeaning.textContent = word.english;
  els.exampleKo.textContent = word.example?.korean || "";
  els.exampleEn.textContent = word.example?.english || "";
  els.traceGuide.textContent = word.korean;

  window.requestAnimationFrame(() => {
    resizeTraceCanvas();
    clearTraceCanvas();
  });

  const youtube = word.media || {};
  const embedUrl = youtubeEmbedUrl(youtube.youtube_url);

  if (embedUrl) {
    els.videoSlot.innerHTML = `<iframe src="${embedUrl}" title="${youtube.youtube_title || word.korean}" allowfullscreen></iframe>`;
    els.youtubeLink.href = youtube.youtube_url;
    els.youtubeLink.textContent = "Open YouTube";
    els.videoMeta.textContent =
      `${youtube.youtube_title || "Verified video"}${youtube.youtube_channel ? ` - ${youtube.youtube_channel}` : ""}`;
  } else {
    const searchUrl =
      youtube.youtube_search_url ||
      `https://www.youtube.com/results?search_query=${encodeURIComponent(`Korean pronunciation ${word.korean}`)}`;

    els.videoSlot.textContent = "Video link not verified yet";
    els.youtubeLink.href = searchUrl;
    els.youtubeLink.textContent = "Search YouTube";
    els.videoMeta.textContent = "Use the search link until this word is enriched.";
  }
}

async function loadModule(moduleNumber) {
  const data = await getJson(`/api/modules/${moduleNumber}/words`);
  state.currentModule = {
    module: data.module,
    module_name: data.module_name,
  };
  state.words = data.words;
  state.index = 0;
  renderModules();
  renderWord();
}

async function startQuiz(mode = "module") {
  state.quizMode = mode;
  state.quizIndex = 0;
  state.score = 0;
  state.isSubmittingQuizAnswer = false;

  const url =
    mode === "final"
      ? "/api/quiz?count=20"
      : `/api/quiz?module=${state.currentModule.module}&count=14`;

  const data = await getJson(url);
  state.quiz = data.questions;
  showQuiz();
  renderQuizQuestion();
}

function renderQuizQuestion() {
  const question = state.quiz[state.quizIndex];

  els.quizFeedback.textContent = "";
  els.typedAnswer.value = "";
  els.quizTitle.textContent =
    state.quizMode === "final"
      ? "Final Review Quiz"
      : `Module ${state.currentModule.module} Quiz`;
  els.scoreBox.textContent = `Score: ${state.score} / ${state.quiz.length}`;

  if (!question) {
    els.quizQuestion.textContent = "Quiz complete.";
    els.quizOptions.innerHTML = "";
    els.typedAnswer.classList.add("hidden");
    els.submitTypedBtn.classList.add("hidden");
    setFeedback(
      els.quizFeedback,
      `Final score: ${state.score} / ${state.quiz.length}`,
      "good"
    );

    els.startQuizBtn.classList.remove("hidden");
    els.startQuizBtn.textContent = "Back to Study";
    els.startQuizBtn.onclick = () => {
      els.startQuizBtn.textContent = "Start Module Quiz";
      els.startQuizBtn.onclick = null;
      showStudy();
    };
    return;
  }

  els.quizQuestion.textContent = `${state.quizIndex + 1}. ${question.prompt}`;
  els.quizOptions.innerHTML = "";

  const hasOptions = Array.isArray(question.options) && question.options.length > 0;

  if (hasOptions) {
    els.typedAnswer.classList.add("hidden");
    els.submitTypedBtn.classList.add("hidden");

    question.options.forEach((option) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "option-button";
      button.textContent = option;
      button.disabled = state.isSubmittingQuizAnswer;
      button.addEventListener("click", () => submitQuizAnswer(option));
      els.quizOptions.appendChild(button);
    });
  } else {
    els.typedAnswer.classList.remove("hidden");
    els.submitTypedBtn.classList.remove("hidden");
  }
}

function getVocabWordForQuestion(question) {
  if (!question || !question.korean_word) return null;
  return state.words.find((word) => word.korean === question.korean_word) || null;
}

async function submitQuizAnswer(answer) {
  const question = state.quiz[state.quizIndex];
  if (!question || state.isSubmittingQuizAnswer) return;

  state.isSubmittingQuizAnswer = true;

  try {
    if (question.type === "multiple_choice") {
      const vocabWord = getVocabWordForQuestion(question);

      const explanation = await postJson("/api/explain-answer", {
        question,
        user_answer: answer,
        vocab_word: vocabWord,
      });

      if (explanation.is_correct) {
        state.score += 1;
      }

      setRichQuizFeedback(explanation);
    } else {
      const correct = normalize(answer) === normalize(question.answer);

      if (correct) {
        state.score += 1;
        setFeedback(els.quizFeedback, "Correct.", "good");
      } else {
        setFeedback(els.quizFeedback, `Incorrect. Answer: ${question.answer}`, "bad");
      }
    }

    els.scoreBox.textContent = `Score: ${state.score} / ${state.quiz.length}`;
    state.quizIndex += 1;
    window.setTimeout(() => {
      state.isSubmittingQuizAnswer = false;
      renderQuizQuestion();
    }, 2200);
  } catch (error) {
    console.error(error);
    setFeedback(els.quizFeedback, `Could not check answer: ${error.message}`, "bad");
    state.isSubmittingQuizAnswer = false;
    renderQuizQuestion();
  }
}

els.prevBtn.addEventListener("click", () => {
  state.index = Math.max(0, state.index - 1);
  renderWord();
});

els.nextBtn.addEventListener("click", () => {
  state.index = Math.min(state.words.length - 1, state.index + 1);
  renderWord();
});

els.clearTraceBtn.addEventListener("click", clearTraceCanvas);
els.traceCanvas.addEventListener("mousedown", startTrace);
els.traceCanvas.addEventListener("mousemove", moveTrace);
window.addEventListener("mouseup", endTrace);
els.traceCanvas.addEventListener("touchstart", startTrace, { passive: false });
els.traceCanvas.addEventListener("touchmove", moveTrace, { passive: false });
els.traceCanvas.addEventListener("touchend", endTrace);

window.addEventListener("resize", () => {
  resizeTraceCanvas();
  clearTraceCanvas();
});

els.startQuizBtn.addEventListener("click", () => startQuiz("module"));
els.finalQuizBtn.addEventListener("click", () => startQuiz("final"));

els.submitTypedBtn.addEventListener("click", () => {
  submitQuizAnswer(els.typedAnswer.value);
});

els.typedAnswer.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    submitQuizAnswer(els.typedAnswer.value);
  }
});

async function init() {
  await fetch("/ingest-vocab", { method: "POST" });
  const data = await getJson("/api/modules");
  state.modules = data.modules;
  renderModules();

  if (state.modules.length > 0) {
    await loadModule(state.modules[0].module);
  } else {
    els.moduleTitle.textContent = "No modules found.";
  }
}

init().catch((error) => {
  els.moduleTitle.textContent = "Could not load CoreKorean.";
  console.error(error);
});