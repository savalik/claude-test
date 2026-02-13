/* ============================================================
   ЭлектроТест — PWA Quiz App
   ============================================================ */

// ─── STATE ───────────────────────────────────────────────────
let questions = [];          // all loaded questions
let progress = {};           // { [id]: { attempts: [{correct: bool, ts}], streak: 0..3, markedUnlearned: bool } }
let shownHistory = [];       // recent shown question ids (anti-repeat)

// Current quiz session
let session = {
  mode: null,                // 'random' | 'ticket' | 'unlearned'
  queue: [],                 // ordered question ids for this session
  index: 0,                  // current position in queue
  answered: false,
  results: [],               // {id, correct}[]
  ticketAnswers: {},         // {idx: correct}
};

const STORAGE_KEY = 'electro_progress_v1';
const HISTORY_LIMIT = 20;
const TICKET_SIZE = 10;
const LEARNED_STREAK = 3;

// ─── STORAGE ─────────────────────────────────────────────────
function saveProgress() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(progress));
  } catch(e) {
    // localStorage might be full or unavailable
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(progress));
    } catch(_) {}
  }
}

function loadProgress() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY) || sessionStorage.getItem(STORAGE_KEY);
    if (raw) progress = JSON.parse(raw);
  } catch(e) { progress = {}; }
}

function getQProgress(id) {
  if (!progress[id]) {
    progress[id] = { attempts: [], streak: 0, markedUnlearned: false };
  }
  return progress[id];
}

function recordAnswer(id, correct) {
  const p = getQProgress(id);
  p.attempts.push({ correct, ts: Date.now() });

  if (correct) {
    p.streak = (p.streak || 0) + 1;
    if (p.streak >= LEARNED_STREAK) {
      p.markedUnlearned = false; // auto-remove from unlearned when learned
    }
  } else {
    p.streak = 0;
  }
  saveProgress();
}

function isLearned(id) {
  const p = progress[id];
  if (!p) return false;
  return p.streak >= LEARNED_STREAK;
}

function getCorrectRate(id) {
  const p = progress[id];
  if (!p || p.attempts.length === 0) return null;
  const correct = p.attempts.filter(a => a.correct).length;
  return Math.round((correct / p.attempts.length) * 100);
}

// ─── SHUFFLE ─────────────────────────────────────────────────
function shuffle(arr) {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

// Anti-repeat queue builder
function buildAntiRepeatQueue(ids) {
  // Filter out recently shown, prefer unseen
  const recent = shownHistory.slice(-HISTORY_LIMIT);
  const notRecent = ids.filter(id => !recent.includes(id));
  const recentInSet = ids.filter(id => recent.includes(id));
  return [...shuffle(notRecent), ...shuffle(recentInSet)];
}

// ─── LOAD QUESTIONS ──────────────────────────────────────────
async function loadQuestions() {
  try {
    const resp = await fetch('results.json');
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    questions = await resp.json();
    return true;
  } catch(e) {
    console.warn('Could not load results.json, using sample data:', e.message);
    questions = getSampleQuestions();
    return true;
  }
}

function getSampleQuestions() {
  return [
    {
      id: 338580,
      question: "На кого распространяются Правила по охране труда при эксплуатации электроустановок?",
      answers: [
        { index: 0, text: "На работников промышленных предприятий, в составе которых имеются электроустановки" },
        { index: 1, text: "На работников организаций независимо от форм собственности и организационно-правовых форм и других физических лиц, занятых техническим обслуживанием электроустановок, проводящих в них оперативные переключения, организующих и выполняющих испытания и измерения" },
        { index: 2, text: "На работодателей - юридических и физических лиц независимо от их организационно-правовых форм и работников из числа электротехнического, электротехнологического и неэлектротехнического персонала" },
        { index: 3, text: "На работников всех организаций независимо от формы собственности, занятых техническим обслуживанием электроустановок и выполняющих в них строительные, монтажные и ремонтные работы" }
      ],
      correct_answer: { index: 2, text: "На работодателей - юридических и физических лиц независимо от их организационно-правовых форм и работников из числа электротехнического, электротехнологического и неэлектротехнического персонала" }
    },
    {
      id: 338581,
      question: "Что является опасным производственным объектом?",
      answers: [
        { index: 0, text: "Предприятия, на которых получаются, используются, перерабатываются, образуются, хранятся, транспортируются, уничтожаются опасные вещества" },
        { index: 1, text: "Любое предприятие независимо от вида деятельности" },
        { index: 2, text: "Только химические и ядерные объекты" },
        { index: 3, text: "Предприятия с количеством работающих более 100 человек" }
      ],
      correct_answer: { index: 0, text: "Предприятия, на которых получаются, используются, перерабатываются, образуются, хранятся, транспортируются, уничтожаются опасные вещества" }
    },
    {
      id: 338582,
      question: "Какое минимальное расстояние должно быть от места работы с электроинструментом до токоведущих частей, находящихся под напряжением до 1000 В?",
      answers: [
        { index: 0, text: "Не менее 0.5 м" },
        { index: 1, text: "Не менее 1 м" },
        { index: 2, text: "Не менее 1.5 м" },
        { index: 3, text: "Расстояние не нормируется" }
      ],
      correct_answer: { index: 0, text: "Не менее 0.5 м" }
    }
  ];
}

// ─── NAVIGATION ──────────────────────────────────────────────
function showView(name) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.getElementById('view-' + name).classList.add('active');
  if (name === 'home') updateHomeStats();
  if (name === 'list') renderList();
}

// ─── HOME STATS ──────────────────────────────────────────────
function updateHomeStats() {
  const total = questions.length;
  const learned = questions.filter(q => isLearned(q.id)).length;
  const pct = total > 0 ? Math.round((learned / total) * 100) : 0;

  document.getElementById('stat-total').textContent = total;
  document.getElementById('stat-learned').textContent = learned;
  document.getElementById('stat-pct').textContent = pct + '%';

  const unlearned = questions.filter(q => !isLearned(q.id) || (progress[q.id] && progress[q.id].markedUnlearned));
  const badge = document.getElementById('unlearned-badge');
  badge.textContent = unlearned.length;
  badge.className = 'mode-badge' + (unlearned.length > 0 ? ' has-items' : '');
}

// ─── MODES ───────────────────────────────────────────────────
function startMode(mode) {
  session.mode = mode;
  session.results = [];
  session.ticketAnswers = {};
  session.index = 0;
  session.answered = false;

  let pool = [];

  if (mode === 'random') {
    pool = questions.map(q => q.id);
    session.queue = buildAntiRepeatQueue(pool);

  } else if (mode === 'ticket') {
    pool = questions.map(q => q.id);
    const shuffled = buildAntiRepeatQueue(pool);
    session.queue = shuffled.slice(0, TICKET_SIZE);
    if (session.queue.length < TICKET_SIZE && questions.length < TICKET_SIZE) {
      session.queue = shuffled; // use all if fewer than 10
    }

  } else if (mode === 'unlearned') {
    const unlPrimary = questions.filter(q => !isLearned(q.id) || (progress[q.id] && progress[q.id].markedUnlearned));
    if (unlPrimary.length === 0) {
      showToast('Все вопросы выучены! 🎉');
      return;
    }
    pool = unlPrimary.map(q => q.id);
    session.queue = buildAntiRepeatQueue(pool);
  }

  if (session.queue.length === 0) {
    showToast('Нет доступных вопросов');
    return;
  }

  // Set up UI
  document.getElementById('quiz-mode-title').textContent =
    mode === 'random' ? 'Случайные вопросы' :
    mode === 'ticket' ? 'Билет #' + (_ticketNum || 1) : 'Не выученные';

  const ticketDots = document.getElementById('ticket-dots');
  ticketDots.style.display = mode === 'ticket' ? 'flex' : 'none';
  if (mode === 'ticket') renderTicketDots();

  showView('quiz');
  renderQuestion();
}

let _ticketNum = 1;
function startNewTicket() {
  _ticketNum++;
  startMode('ticket');
}

// ─── TICKET DOTS ─────────────────────────────────────────────
function renderTicketDots() {
  const container = document.getElementById('ticket-dots');
  document.getElementById('quiz-mode-title').textContent = 'Билет #' + (_ticketNum || 1);
  container.innerHTML = '';
  session.queue.forEach((id, i) => {
    const dot = document.createElement('div');
    dot.className = 'ticket-dot';
    dot.id = 'td-' + i;
    dot.textContent = i + 1;
    dot.onclick = () => jumpToTicketQ(i);
    container.appendChild(dot);
  });
  updateTicketDots();
}

function updateTicketDots() {
  session.queue.forEach((id, i) => {
    const dot = document.getElementById('td-' + i);
    if (!dot) return;
    dot.className = 'ticket-dot';
    if (i === session.index) dot.classList.add('current');
    else if (session.ticketAnswers[i] === true) dot.classList.add('answered-correct');
    else if (session.ticketAnswers[i] === false) dot.classList.add('answered-wrong');
  });
}

function jumpToTicketQ(i) {
  if (!session.answered && session.ticketAnswers[session.index] === undefined) {
    // Don't allow jumping if current unanswered
  }
  session.index = i;
  session.answered = session.ticketAnswers[i] !== undefined;
  renderQuestion();
}

// ─── RENDER QUESTION ─────────────────────────────────────────
function renderQuestion() {
  if (session.index >= session.queue.length) {
    finishSession();
    return;
  }

  const qId = session.queue[session.index];
  const q = questions.find(x => x.id === qId);
  if (!q) { nextQuestion(); return; }

  // Add to shown history
  shownHistory.push(qId);
  if (shownHistory.length > HISTORY_LIMIT * 2) shownHistory = shownHistory.slice(-HISTORY_LIMIT);

  session.answered = false;

  // Progress bar
  const pct = (session.index / session.queue.length) * 100;
  document.getElementById('quiz-progress').style.width = pct + '%';

  // Badge
  document.getElementById('quiz-badge').textContent =
    (session.index + 1) + '/' + session.queue.length;

  // Counter
  document.getElementById('quiz-counter').textContent = 'Вопрос ' + (session.index + 1);

  // Question
  document.getElementById('question-id-label').textContent = 'Вопрос #' + q.id;
  document.getElementById('question-text').textContent = q.question;

  // Streak dots
  const p = getQProgress(qId);
  const streak = p.streak || 0;
  for (let i = 0; i < 3; i++) {
    const dot = document.getElementById('sd' + i);
    dot.className = 'streak-dot' + (i < streak ? ' filled' : '');
  }

  // Shuffle answers
  const shuffledAnswers = shuffle(q.answers);

  // Answers
  const letters = ['А', 'Б', 'В', 'Г', 'Д', 'Е'];
  const list = document.getElementById('answers-list');
  list.innerHTML = '';
  shuffledAnswers.forEach((ans, i) => {
    const btn = document.createElement('button');
    btn.className = 'answer-btn';
    btn.innerHTML = `
      <div class="answer-letter">${letters[i]}</div>
      <div class="answer-text">${ans.text}</div>
    `;
    btn.onclick = () => selectAnswer(ans.index, q.correct_answer.index, q.id, shuffledAnswers);
    list.appendChild(btn);
  });

  // Result panel
  const rp = document.getElementById('result-panel');
  rp.className = 'quiz-result-panel';

  // If already answered in ticket mode
  if (session.mode === 'ticket' && session.ticketAnswers[session.index] !== undefined) {
    session.answered = true;
    // Re-show state but don't re-record
    showAnsweredState(q, shuffledAnswers, session.ticketAnswers[session.index]);
  }

  // Next button
  const btnNext = document.getElementById('btn-next');
  btnNext.disabled = !session.answered;
  if (session.mode === 'ticket') {
    // Check if all answered
    const allAnswered = session.queue.every((_, i) => session.ticketAnswers[i] !== undefined);
    btnNext.textContent = allAnswered ? 'Результаты →' : 'Следующий →';
  } else {
    btnNext.textContent = session.index < session.queue.length - 1 ? 'Следующий →' : 'Завершить →';
  }

  updateTicketDots();
}

function showAnsweredState(q, shuffledAnswers, wasCorrect) {
  const list = document.getElementById('answers-list');
  const btns = list.querySelectorAll('.answer-btn');
  btns.forEach((btn, i) => {
    btn.disabled = true;
    const ansIndex = shuffledAnswers[i].index;
    if (ansIndex === q.correct_answer.index) {
      btn.classList.add('correct');
    } else if (!wasCorrect && btn.classList.contains('selected')) {
      btn.classList.add('wrong');
    }
  });

  const rp = document.getElementById('result-panel');
  if (wasCorrect) {
    rp.className = 'quiz-result-panel correct';
    document.getElementById('result-icon').textContent = '✓';
    document.getElementById('result-text').innerHTML = '<strong>Правильно!</strong>Отличный результат';
  } else {
    rp.className = 'quiz-result-panel wrong';
    document.getElementById('result-icon').textContent = '✗';
    document.getElementById('result-text').innerHTML =
      '<strong>Неверно</strong>Правильный ответ выделен зелёным';
  }
}

// ─── SELECT ANSWER ───────────────────────────────────────────
function selectAnswer(selectedIndex, correctIndex, qId, shuffledAnswers) {
  if (session.answered) return;
  session.answered = true;

  const correct = selectedIndex === correctIndex;
  recordAnswer(qId, correct);

  // Update streak dots
  const p = getQProgress(qId);
  const streak = p.streak || 0;
  for (let i = 0; i < 3; i++) {
    const dot = document.getElementById('sd' + i);
    dot.className = 'streak-dot' + (i < streak ? ' filled' : '');
  }

  // Style buttons
  const list = document.getElementById('answers-list');
  const btns = list.querySelectorAll('.answer-btn');
  btns.forEach((btn, i) => {
    btn.disabled = true;
    const ansIndex = shuffledAnswers[i].index;
    if (ansIndex === correctIndex) {
      btn.classList.add('correct');
    } else if (ansIndex === selectedIndex) {
      btn.classList.add('wrong');
    }
  });

  // Result panel
  const rp = document.getElementById('result-panel');
  const ri = document.getElementById('result-icon');
  const rt = document.getElementById('result-text');

  if (correct) {
    rp.className = 'quiz-result-panel correct';
    ri.textContent = '✓';
    const msgs = ['Правильно!', 'Верно!', 'Отлично!', 'Так держать!'];
    rt.innerHTML = `<strong>${msgs[Math.floor(Math.random()*msgs.length)]}</strong>${streak >= LEARNED_STREAK ? '🔥 Вопрос выучен!' : `Серия: ${streak}/3`}`;
  } else {
    rp.className = 'quiz-result-panel wrong';
    ri.textContent = '✗';
    rt.innerHTML = '<strong>Неверно</strong>Правильный ответ выделен зелёным';
  }

  // Save to session results
  session.results.push({ id: qId, correct });

  // Ticket mode tracking
  if (session.mode === 'ticket') {
    session.ticketAnswers[session.index] = correct;
    updateTicketDots();
    const allAnswered = session.queue.every((_, i) => session.ticketAnswers[i] !== undefined);
    document.getElementById('btn-next').textContent = allAnswered ? 'Результаты →' : 'Следующий →';
  } else {
    document.getElementById('btn-next').textContent =
      session.index < session.queue.length - 1 ? 'Следующий →' : 'Завершить →';
  }

  document.getElementById('btn-next').disabled = false;
}

// ─── NEXT QUESTION ───────────────────────────────────────────
function nextQuestion() {
  if (!session.answered && session.mode !== 'ticket') {
    showToast('Выберите ответ');
    return;
  }

  if (session.mode === 'ticket') {
    // Find next unanswered question
    const allAnswered = session.queue.every((_, i) => session.ticketAnswers[i] !== undefined);
    if (allAnswered) {
      finishSession();
      return;
    }
    // Find next unanswered
    let next = session.index + 1;
    while (next < session.queue.length && session.ticketAnswers[next] !== undefined) next++;
    if (next >= session.queue.length) {
      // wrap around
      next = 0;
      while (next < session.queue.length && session.ticketAnswers[next] !== undefined) next++;
    }
    session.index = next;
  } else {
    session.index++;
    if (session.index >= session.queue.length) {
      finishSession();
      return;
    }
  }

  renderQuestion();
}

function skipQuestion() {
  if (session.mode === 'ticket') {
    nextQuestion();
    return;
  }
  // In random/unlearned: skip moves to end of queue
  const qId = session.queue.splice(session.index, 1)[0];
  session.queue.push(qId);
  if (session.index >= session.queue.length) session.index = 0;
  renderQuestion();
  showToast('Вопрос пропущен');
}

// ─── FINISH SESSION ──────────────────────────────────────────
function finishSession() {
  // In random/unlearned, might be infinite - show after X questions
  const correct = session.results.filter(r => r.correct).length;
  const total = session.results.length;
  if (total === 0) { showView('home'); return; }

  const pct = Math.round((correct / total) * 100);
  const scoreEl = document.getElementById('results-score-pct');
  scoreEl.textContent = pct + '%';
  scoreEl.className = 'results-score ' + (pct >= 80 ? 'great' : pct >= 50 ? 'ok' : 'bad');

  const msgs = pct >= 90 ? ['🏆 Превосходно!', '🌟 Блестяще!'] :
               pct >= 70 ? ['👍 Хорошо!', '✅ Молодец!'] :
               pct >= 50 ? ['📚 Неплохо', '🔄 Продолжай учиться'] :
               ['💪 Не сдавайся!', '📖 Повтори материал'];
  document.getElementById('results-msg').textContent = msgs[Math.floor(Math.random()*msgs.length)];

  document.getElementById('res-correct').textContent = correct;
  document.getElementById('res-wrong').textContent = total - correct;

  updateHomeStats();
  showView('results');
}

function restartQuiz() {
  startMode(session.mode);
}

// ─── EXIT QUIZ ───────────────────────────────────────────────
function confirmExitQuiz() {
  if (session.results.length > 0) {
    if (confirm('Выйти из тренировки? Прогресс текущей сессии будет сохранён.')) {
      showView('home');
    }
  } else {
    showView('home');
  }
}

// ─── QUESTIONS LIST ──────────────────────────────────────────
function renderList() {
  const query = (document.getElementById('list-search')?.value || '').toLowerCase();
  const filtered = questions.filter(q =>
    !query || q.question.toLowerCase().includes(query)
  );

  document.getElementById('list-badge').textContent = questions.length;

  const scroll = document.getElementById('list-scroll');
  if (filtered.length === 0) {
    scroll.innerHTML = '<div class="empty-state"><div class="empty-icon">🔍</div><div class="empty-title">Ничего не найдено</div><div class="empty-desc">Попробуйте другой запрос</div></div>';
    return;
  }

  // Virtual rendering for performance with large lists
  scroll.innerHTML = '';
  const fragment = document.createDocumentFragment();

  filtered.forEach((q, i) => {
    const p = getQProgress(q.id);
    const rate = getCorrectRate(q.id);
    const learned = isLearned(q.id);
    const marked = p.markedUnlearned || false;

    const item = document.createElement('div');
    item.className = 'question-list-item';

    const rateClass = rate === null ? '' : rate >= 70 ? 'high' : rate >= 40 ? 'mid' : 'low';
    const rateStr = rate === null ? '—' : rate + '%';

    const streakHtml = [0,1,2].map(i =>
      `<div class="qli-streak-dot ${(p.streak||0) > i ? 'ok' : ''}"></div>`
    ).join('');

    item.innerHTML = `
      <div class="qli-num">#${i + 1}</div>
      <div class="qli-text">${q.question}</div>
      <div class="qli-right">
        <div class="qli-pct ${rateClass}">${rateStr}</div>
        <div class="qli-streak">${streakHtml}</div>
        <div class="qli-star ${marked ? 'marked' : ''}" onclick="toggleMark(event, ${q.id})" title="Добавить в не выученные">★</div>
      </div>
    `;
    item.addEventListener('click', (e) => {
      if (!e.target.classList.contains('qli-star')) {
        startSingleQuestion(q.id);
      }
    });
    fragment.appendChild(item);
  });

  scroll.appendChild(fragment);
}

function toggleMark(e, qId) {
  e.stopPropagation();
  const p = getQProgress(qId);
  p.markedUnlearned = !p.markedUnlearned;
  if (p.markedUnlearned && p.streak >= LEARNED_STREAK) {
    p.streak = 0; // reset streak when manually marking
  }
  saveProgress();
  renderList();
  updateHomeStats();
  showToast(p.markedUnlearned ? 'Добавлено в не выученные ★' : 'Убрано из не выученных');
}

function startSingleQuestion(qId) {
  session.mode = 'random';
  session.results = [];
  session.index = 0;
  session.answered = false;
  session.queue = [qId];
  session.ticketAnswers = {};

  document.getElementById('quiz-mode-title').textContent = 'Вопрос';
  document.getElementById('ticket-dots').style.display = 'none';
  showView('quiz');
  renderQuestion();
}

// ─── TOAST ───────────────────────────────────────────────────
let toastTimer;
function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('show'), 2200);
}

// ─── INIT ────────────────────────────────────────────────────
async function init() {
  loadProgress();
  const ok = await loadQuestions();
  if (!ok || questions.length === 0) {
    document.getElementById('loading').innerHTML = `
      <div style="text-align:center;padding:40px;color:#e84560">
        <div style="font-size:48px">⚡</div>
        <div style="font-size:18px;font-weight:700;margin-top:16px">Ошибка загрузки</div>
        <div style="font-size:14px;color:#9898b8;margin-top:8px">Файл results.json не найден рядом с index.html</div>
      </div>`;
    return;
  }

  updateHomeStats();
  document.getElementById('loading').style.opacity = '0';
  setTimeout(() => {
    document.getElementById('loading').style.display = 'none';
    document.getElementById('view-home').classList.add('active');
  }, 400);
  document.getElementById('loading').style.transition = 'opacity .4s';
}

init();

// ─── SERVICE WORKER REGISTRATION ─────────────────────────────
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('sw.js').catch(() => {});
  });
}
