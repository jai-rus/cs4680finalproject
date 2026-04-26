const state = {
  modules: [],
  currentModule: null,
  words: [],
  index: 0,
  quiz: [],
  quizIndex: 0,
  score: 0,
  quizMode: "module",
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
  quizReview: document.querySelector("#quizReview"),
  nextQuizBtn: document.querySelector("#nextQuizBtn"),
};

const trace = {
  drawing: false,
  ctx: null,
};

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
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${url}`);
  }
  return response.json();
}

function setFeedback(element, message, kind = "") {
  element.textContent = message;
  element.className = `feedback ${kind}`.trim();
}

function resizeTraceCanvas() {
  const canvas = els.traceCanvas;
  const rect = canvas.getBoundingClientRect();
  const scale = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.floor(rect.width * scale));
  canvas.height = Math.max(1, Math.floor(rect.height * scale));
  trace.ctx = canvas.getContext("2d");
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

  const youtube = word.youtube || {};
  const embedUrl = youtubeEmbedUrl(youtube.url);
  if (embedUrl) {
    els.videoSlot.innerHTML = `<iframe src="${embedUrl}" title="${youtube.title || word.korean}" allowfullscreen></iframe>`;
    els.youtubeLink.href = youtube.url;
    els.youtubeLink.textContent = "Open YouTube";
    els.videoMeta.textContent = `${youtube.title || "Verified video"}${youtube.channel ? ` - ${youtube.channel}` : ""}`;
  } else {
    const searchUrl = youtube.search_url || `https://www.youtube.com/results?search_query=${encodeURIComponent(`Korean pronunciation ${word.korean}`)}`;
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
  const url = mode === "final"
    ? "/api/quiz?count=20"
    : `/api/quiz?module=${state.currentModule.module}&count=14`;
  const data = await getJson(url);
  state.quiz = data.questions;
  showQuiz();
  renderQuizQuestion();
}

function addQuizAction(label, onClick, primary = false) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = primary ? "option-button primary" : "option-button";
  button.textContent = label;
  button.addEventListener("click", onClick);
  els.quizOptions.appendChild(button);
}

function renderQuizComplete() {
  const total = state.quiz.length;
  const required = Math.ceil(total * 0.6);
  const percent = Math.round((state.score / total) * 100);
  const passed = state.score >= required;

  els.quizQuestion.textContent = "Quiz complete.";
  els.quizOptions.innerHTML = "";
  els.typedAnswer.classList.add("hidden");
  els.submitTypedBtn.classList.add("hidden");
  els.nextQuizBtn.classList.add("hidden");

  if (state.quizMode === "final") {
    setFeedback(els.quizFeedback, `Final score: ${state.score} / ${total} (${percent}%).`, "good");
    addQuizAction("Back to Study", showStudy, true);
    return;
  }

  if (passed) {
    setFeedback(
      els.quizFeedback,
      `Passed: ${state.score} / ${total} (${percent}%). You can move to the next module.`,
      "good"
    );
    const currentModule = Number(state.currentModule.module);
    const nextModule = state.modules.find((module) => Number(module.module) === currentModule + 1);
    if (nextModule) {
      addQuizAction("Next module", () => loadModule(nextModule.module), true);
    } else {
      addQuizAction("Final Review Quiz", () => startQuiz("final"), true);
    }
    addQuizAction("Back to Study", showStudy);
    return;
  }

  setFeedback(
    els.quizFeedback,
    `Score: ${state.score} / ${total} (${percent}%). You need ${required} correct answers to pass.`,
    "bad"
  );
  addQuizAction("Retry quiz", () => startQuiz("module"), true);
  addQuizAction("Back to Study", showStudy);
}

function renderQuizQuestion() {
  const question = state.quiz[state.quizIndex];
  els.quizFeedback.textContent = "";
  els.quizReview.textContent = "";
  els.typedAnswer.value = "";
  els.typedAnswer.disabled = false;
  els.submitTypedBtn.disabled = false;
  els.nextQuizBtn.classList.add("hidden");
  els.quizTitle.textContent = state.quizMode === "final" ? "Final Review Quiz" : `Module ${state.currentModule.module} Quiz`;
  els.scoreBox.textContent = `Score: ${state.score} / ${state.quiz.length}`;

  if (!question) {
    renderQuizComplete();
    return;
  }

  els.typedAnswer.classList.remove("hidden");
  els.submitTypedBtn.classList.remove("hidden");
  els.quizQuestion.textContent = `${state.quizIndex + 1}. ${question.prompt}`;
  els.quizOptions.innerHTML = "";
  question.options.forEach((option) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "option-button";
    button.textContent = option;
    button.addEventListener("click", () => submitQuizAnswer(option));
    els.quizOptions.appendChild(button);
  });
}

async function submitQuizAnswer(answer) {
  const question = state.quiz[state.quizIndex];
  if (!question) return;
  if (!answer.trim()) return;

  const optionButtons = els.quizOptions.querySelectorAll("button");
  optionButtons.forEach((button) => {
    button.disabled = true;
  });
  els.typedAnswer.disabled = true;
  els.submitTypedBtn.disabled = true;

  const result = await postJson("/api/check-answer", {
    question,
    user_answer: answer,
  });

  if (result.is_correct) {
    state.score += 1;
    setFeedback(els.quizFeedback, result.feedback || "Correct.", "good");
  } else {
    setFeedback(els.quizFeedback, result.feedback || `Incorrect. Answer: ${question.answer}`, "bad");
  }
  els.quizReview.textContent = result.review || "";

  els.nextQuizBtn.textContent = state.quizIndex + 1 >= state.quiz.length ? "Show score" : "Next question";
  els.nextQuizBtn.classList.remove("hidden");
}

els.nextQuizBtn.addEventListener("click", () => {
  state.quizIndex += 1;
  renderQuizQuestion();
});

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
els.submitTypedBtn.addEventListener("click", () => submitQuizAnswer(els.typedAnswer.value));
els.typedAnswer.addEventListener("keydown", (event) => {
  if (event.key === "Enter") submitQuizAnswer(els.typedAnswer.value);
});

async function init() {
  await fetch("/ingest-vocab", { method: "POST" });
  const data = await getJson("/api/modules");
  state.modules = data.modules;
  renderModules();
  await loadModule(state.modules[0].module);
}

init().catch((error) => {
  els.moduleTitle.textContent = "Could not load CoreKorean.";
  console.error(error);
});
