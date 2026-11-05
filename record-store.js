// Local learning records only. Failed writes remain available for export in this tab.
(() => {
  "use strict";
  const memory = new Map();
  const recovered = Object.create(null);
  const questionIds = new Set((window.QUIZ_DATA?.questions || []).map(q => q.id));
  const subjects = new Set((window.QUIZ_DATA?.questions || []).map(q => q.subject));
  const electives = ["청소년이해론", "청소년수련활동론"];
  const object = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const count = v => Number.isSafeInteger(v) && v >= 0;
  const date = v => typeof v === "string" && /^\d{4}-\d{2}-\d{2}$/.test(v) &&
    Number.isFinite(Date.parse(`${v}T00:00:00Z`)) && new Date(`${v}T00:00:00Z`).toISOString().slice(0, 10) === v;
  const timestamp = v => typeof v === "string" && Number.isFinite(Date.parse(v));
  const strings = v => Array.isArray(v) && v.every(x => typeof x === "string");
  const ids = v => strings(v) && v.every(id => questionIds.has(id));
  const mockRecord = r => object(r) && typeof r.id === "string" && count(r.year) &&
    [1, 2].includes(r.session) && electives.includes(r.elective) &&
    (r.attemptId === undefined || typeof r.attemptId === "string") &&
    timestamp(r.startedAt) && timestamp(r.finishedAt) && strings(r.subjects) &&
    r.subjects.every(s => subjects.has(s)) && object(r.scores) &&
    r.subjects.every(s => object(r.scores[s]) && count(r.scores[s].correct) && count(r.scores[s].total) &&
      r.scores[s].correct <= r.scores[s].total && r.scores[s].total <= 25) &&
    Array.isArray(r.answers) && r.answers.length <= 100 && r.answers.every(a =>
      object(a) && typeof a.id === "string" && subjects.has(a.subject) && [1,2].includes(a.session) &&
      count(a.number) && typeof a.prompt === "string" && typeof a.selectedText === "string" &&
      (a.selectedOriginal === null || (Number.isInteger(a.selectedOriginal) && a.selectedOriginal >= 1 && a.selectedOriginal <= 5)) &&
      Array.isArray(a.correctOriginals) && a.correctOriginals.length > 0 && a.correctOriginals.every(n => Number.isInteger(n) && n >= 1 && n <= 5) &&
      strings(a.correctTexts) && a.correctTexts.length === a.correctOriginals.length && typeof a.correct === "boolean");
  function valid(key, value) {
    if (key === "mindGrowHistory") return object(value) && count(value.solved) && count(value.correct) &&
      (value.solvedQuestionIds === undefined || ids(value.solvedQuestionIds));
    if (key === "mindGrowWrongBook") return Array.isArray(value) && value.every(v => object(v) && questionIds.has(v.id) && date(v.availableOn) &&
      (v.reviewStage === undefined || (count(v.reviewStage) && v.reviewStage < 4)) &&
      (v.reviewStartedOn === undefined || date(v.reviewStartedOn)));
    if (key === "mindGrowMockExamHistory") return Array.isArray(value) && value.length <= 80 && value.every(mockRecord);
    if (key === "mindGrowElectiveSubject") return electives.includes(value);
    if (electives.some(s => key === `mindGrowDailySeen:${s}`)) return ids(value);
    return false;
  }
  const known = key => ["mindGrowHistory", "mindGrowWrongBook", "mindGrowMockExamHistory", "mindGrowElectiveSubject",
    ...electives.map(s => `mindGrowDailySeen:${s}`)].includes(key);
  function notice(message) {
    const el = document.getElementById("storageNotice");
    if (el) { el.hidden = false; el.textContent = message; }
  }
  function raw(key) {
    if (memory.has(key)) return memory.get(key);
    try { return localStorage.getItem(key); }
    catch { notice("이 브라우저에서 기록 저장소를 사용할 수 없어요. 창을 닫기 전에 학습 기록을 내보내 주세요."); return null; }
  }
  function write(key, value) {
    memory.set(key, value);
    try { localStorage.setItem(key, value); return true; }
    catch { notice("기록을 기기에 저장하지 못했어요. 현재 창에서는 계속 학습할 수 있어요. 창을 닫기 전에 학습 기록을 내보내 주세요."); return false; }
  }
  function read(key, fallback) {
    const value = raw(key);
    if (value === null) return fallback;
    try {
      const parsed = key === "mindGrowElectiveSubject" ? value : JSON.parse(value);
      if (!valid(key, parsed)) throw new Error("Invalid record");
      return parsed;
    } catch {
      recovered[key] = value;
      // Preserve the original bytes before a later normal save replaces the invalid key.
      let archive = {};
      try { const existing = JSON.parse(raw("mindGrowRecovery") || "{}"); if (object(existing)) archive = existing; } catch {}
      write("mindGrowRecovery", JSON.stringify({...archive, [key]: value}));
      notice("일부 학습 기록을 읽지 못해 기본값으로 열었어요. 손상된 원본은 보존했으며 학습 기록 내보내기에 함께 포함됩니다.");
      return fallback;
    }
  }
  function backup() {
    const records = Object.create(null);
    const keys = ["mindGrowHistory", "mindGrowWrongBook", "mindGrowMockExamHistory", "mindGrowElectiveSubject",
      ...electives.map(s => `mindGrowDailySeen:${s}`)];
    for (const key of keys) {
      const value = read(key, null);
      if (value !== null) records[key] = value;
    }
    let recovery = {};
    try { const parsed = JSON.parse(raw("mindGrowRecovery") || "{}"); if (object(parsed)) recovery = parsed; } catch {}
    return {format: "mind-grow-records", version: 1, exportedAt: new Date().toISOString(), records,
      recovery: {...recovery, ...recovered}};
  }
  function validateBackup(value) {
    if (!object(value) || value.format !== "mind-grow-records" || value.version !== 1 || !object(value.records) ||
        !Object.entries(value.records).every(([k,v]) => known(k) && valid(k,v)) ||
        (value.recovery !== undefined && (!object(value.recovery) || !Object.values(value.recovery).every(v => typeof v === "string")))) {
      throw new Error("백업 파일 형식이나 기록 내용을 확인해 주세요. 현재 기록은 변경하지 않았어요.");
    }
    return value;
  }
  function restore(value) {
    validateBackup(value);
    const keys = ["mindGrowHistory", "mindGrowWrongBook", "mindGrowMockExamHistory", "mindGrowElectiveSubject",
      ...electives.map(s => `mindGrowDailySeen:${s}`), "mindGrowRecovery"];
    const before = new Map(keys.map(key => [key, localStorage.getItem(key)]));
    try {
      // Store nonempty values first so a quota failure occurs before removing old keys.
      const incoming = {...value.records, mindGrowRecovery: value.recovery || {}};
      for (const [key, entry] of Object.entries(incoming)) localStorage.setItem(key,
        key === "mindGrowElectiveSubject" ? entry : JSON.stringify(entry));
      for (const key of keys) if (!Object.hasOwn(incoming, key)) localStorage.removeItem(key);
    } catch {
      for (const [key, old] of before) {
        if (old === null) { try { localStorage.removeItem(key); } catch {} }
      }
      const rollback = [...before].filter(([, old]) => old !== null);
      rollback.sort(([a, av], [b, bv]) =>
        (av.length - (localStorage.getItem(a)?.length || 0)) - (bv.length - (localStorage.getItem(b)?.length || 0)));
      for (const [key, old] of rollback) {
        try { if (old === null) localStorage.removeItem(key); else localStorage.setItem(key, old); } catch {}
      }
      throw new Error("기록을 가져오지 못했어요. 기기의 저장 공간과 브라우저 설정을 확인해 주세요.");
    }
    memory.clear();
  }
  window.MindGrowRecords = {read, write, backup, validateBackup, restore,
    save: (key, value) => write(key, JSON.stringify(value))};
})();
