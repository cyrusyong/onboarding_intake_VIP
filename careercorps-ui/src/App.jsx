import { useEffect, useMemo, useState, useRef } from "react";
import * as pdfjsLib from "pdfjs-dist";
import pdfWorkerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import "./App.css";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";
const ACCEPTED_RESUME_EXTENSIONS = [".pdf", ".txt", ".md", ".rtf"];

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

const STEPS = [
  {
    id: 1,
    label: "Your story",
    note: "Describe your situation.",
  },
  {
    id: 2,
    label: "More details",
    note: "Answer a few questions.",
  },
  {
    id: 3,
    label: "JSON",
    note: "Review your result.",
  },
];

const FIELD_LABELS = {
  target_role: "Career goal",
  transition_type: "Transition",
  job_responsibilities: "Desired work",
  job_requirements: "Requirements",
  education_background: "Education",
  work_background: "Experience",
  target_field_experience: "Field experience",
  known_gaps: "Known gaps",
  skills: "Strengths",
  projects: "Projects",
  learning_style: "Learning style",
  hours_per_week: "Weekly time",
  childcare_constraints: "Childcare",
  healthcare_constraints: "Healthcare",
  housing_constraints: "Housing",
  learning_budget: "Budget",
  pcs_expected: "PCS plans",
};

function simplifyQuestion(question, key) {
  if (!question) {
    return `Tell us about ${fieldLabel(key).toLowerCase()}.`;
  }

  const normalized = question
    .replace(/\s+,/g, ",")
    .replace(/,\s*\?/g, "?")
    .replace(/\s+\?/g, "?")
    .replace(/\s{2,}/g, " ")
    .trim();

  const clean = normalized.endsWith("?") ? normalized : `${normalized}?`;
  return clean
    .replace(/\s+,/g, ",")
    .replace(/,\s*\?/g, "?")
    .replace(/\s+\?/g, "?")
    .replace(/\s{2,}/g, " ")
    .replace(/^./, (char) => char.toUpperCase());
}

function fieldLabel(key) {
  return FIELD_LABELS[key] || key;
}

function parseAsList(value, key) {
  const listFields = ["skills", "job_requirements", "projects"];

  if (Array.isArray(value)) {
    if (value.length > 1) return value;
    return null;
  }

  if (listFields.includes(key) && typeof value === "string" && value.includes(",")) {
    const parts = value.split(",").map((s) => s.trim()).filter(Boolean);
    if (parts.length > 1 && parts.every((p) => p.split(" ").length < 8)) {
      return parts;
    }
  }
  return null;
}

function valueLabel(value) {
  if (value === null || value === undefined || value === "" || (Array.isArray(value) && value.length === 0)) {
    return "Still needed";
  }
  if (Array.isArray(value)) {
    return value.join(", ");
  }
  return String(value);
}

function extensionForFile(fileName) {
  const match = String(fileName).toLowerCase().match(/(\.[a-z0-9]+)$/);
  return match ? match[1] : "";
}

function stripRtf(text) {
  return String(text)
    .replace(/\\par[d]?/g, "\n")
    .replace(/\\'[0-9a-f]{2}/gi, " ")
    .replace(/\\[a-z]+-?\d* ?/gi, " ")
    .replace(/[{}]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function normalizeResumeText(rawText, fileName) {
  const extension = extensionForFile(fileName);
  const text = extension === ".rtf" ? stripRtf(rawText) : String(rawText);
  return text.replace(/\r\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
}

async function extractPdfText(file) {
  const buffer = await file.arrayBuffer();
  const pdf = await pdfjsLib.getDocument({ data: buffer }).promise;
  const pages = [];

  for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber += 1) {
    const page = await pdf.getPage(pageNumber);
    const content = await page.getTextContent();
    const text = content.items
      .map((item) => ("str" in item ? item.str : ""))
      .join(" ")
      .replace(/\s+/g, " ")
      .trim();

    if (text) {
      pages.push(text);
    }
  }

  return pages.join("\n\n").trim();
}

function shortenText(value, maxLen = 180) {
  const compact = String(value).replace(/\s+/g, " ").trim().replace(/[ ,.;:]+$/g, "");
  if (compact.length <= maxLen) {
    return compact;
  }
  const shortened = compact.slice(0, maxLen).replace(/\s+\S*$/, "").replace(/[ ,.;:]+$/g, "");
  return `${shortened}...`;
}

function cleanTextValue(text, maxLen = 180) {
  const compact = String(text)
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^(i am|i'm|i have|i need|my|our|we have|we need)\s+/i, "")
    .replace(/[ ,.;:]+$/g, "");

  if (!compact) {
    return null;
  }

  return shortenText(compact.charAt(0).toUpperCase() + compact.slice(1), maxLen);
}

function applyFieldFallbacks(values) {
  const normalized = { ...values };

  if (!normalized.target_role && normalized.job_responsibilities) {
    normalized.target_role = normalized.job_responsibilities;
  }

  if (!normalized.job_responsibilities && normalized.target_role) {
    normalized.job_responsibilities = normalized.target_role;
  }

  if (!normalized.target_field_experience && normalized.work_background) {
    normalized.target_field_experience = normalized.work_background;
  }

  return normalized;
}

function normalizeFieldValue(key, value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }

  if (Array.isArray(value)) {
    return value.map((v) => normalizeFieldValue(key, v)).filter(Boolean);
  }

  const text = String(value).trim();

  if (key === "hours_per_week") {
    const match = text.match(/\b(\d{1,2})\b/);
    return match ? Number(match[1]) : shortenText(text, 40);
  }

  if (key === "learning_budget") {
    const match = text.match(/\$?\s*([0-9]{2,5})/);
    if (match) {
      return `$${match[1]}`;
    }
  }

  if (key === "target_role") {
    const cleaned = text
      .replace(/^(i want to be|i want|working toward|hoping for|looking for|interested in)\s+/i, "")
      .trim();
    return cleanTextValue(cleaned, 120);
  }

  if (
    [
      "transition_type",
      "job_responsibilities",
      "job_requirements",
      "education_background",
      "work_background",
      "target_field_experience",
      "known_gaps",
      "skills",
      "projects",
      "learning_style",
      "childcare_constraints",
      "healthcare_constraints",
      "housing_constraints",
      "pcs_expected",
    ].includes(key)
  ) {
    return cleanTextValue(text, 180);
  }

  return cleanTextValue(text, 140);
}

function mergeOverview(base, answers, formattedAnswers = {}) {
  if (!base) {
    return null;
  }

  const merged = Object.fromEntries(
    Object.entries(base).map(([key, value]) => [key, normalizeFieldValue(key, value)]),
  );

  for (const [key, value] of Object.entries(answers)) {
    const finalValue = formattedAnswers[key] !== undefined ? formattedAnswers[key] : value;
    if (finalValue && (Array.isArray(finalValue) ? finalValue.length > 0 : String(finalValue).trim())) {
      merged[key] = normalizeFieldValue(key, finalValue);
    }
  }
  return applyFieldFallbacks(merged);
}

function buildConversation(step, analysis, groupedMissingFields, activeQuestionTab) {
  if (step === 1) {
    return [
      {
      role: "guide",
      title: "Start here",
      body:
        "Describe your goals, your experience, and anything making things difficult right now. You can also upload a text resume.",},
    ];
  }

  if (step === 2 && analysis?.missingFields?.length) {
    const activeGroup =
      groupedMissingFields.find((group) => group.key === activeQuestionTab) ||
      groupedMissingFields[0];

    if (!activeGroup) {
      return [
        {
          role: "guide",
          title: "Your overview is ready",
          body: "Your summary is on the right. You can save it now.",
        },
      ];
    }

    return [
      {
      role: "guide",
      title: activeGroup.title,
      body:
        `${activeGroup.description} Your overview on the right updates as you answer.`,
      },
    ];
  }

  if (step === 3) {
    return [
      {
        role: "guide",
        title: "All set",
        body: "Your saved JSON is below.",
      },
    ];
  }

  return [];
}

function App() {
  const [story, setStory] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [analysis, setAnalysis] = useState(null);
  const [answers, setAnswers] = useState({});
  const [formattedAnswers, setFormattedAnswers] = useState({});
  const [finalPayload, setFinalPayload] = useState(null);
  const [currentStep, setCurrentStep] = useState(1);
  const [saveState, setSaveState] = useState("idle");
  const [activeQuestionTab, setActiveQuestionTab] = useState("critical");
  const [sampleLoading, setSampleLoading] = useState(false);
  const [sampleAnswersLoading, setSampleAnswersLoading] = useState(false);
  const [resumeText, setResumeText] = useState("");
  const [resumeFileName, setResumeFileName] = useState("");
  const [resumeError, setResumeError] = useState("");
  const lastSourceRef = useRef({ story: "", resumeText: "", sentenceCount: 0 });

  const currentSentenceCount = (story.match(/[.!?\n]+/g) || []).length;

  useEffect(() => {
    if (currentStep !== 1) return;
    const currentStory = story.trim();
    const currentResume = resumeText.trim();

    if (!currentStory && !currentResume) return;

    if (
      lastSourceRef.current.story === currentStory &&
      lastSourceRef.current.resumeText === currentResume
    ) {
      return;
    }

    if (
      lastSourceRef.current.resumeText === currentResume &&
      lastSourceRef.current.sentenceCount === currentSentenceCount
    ) {
      return;
    }

    const controller = new AbortController();

    const timeoutId = setTimeout(async () => {
      try {
        const response = await fetch(`${API_BASE}/api/intake/start`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ story: currentStory, resumeText: currentResume }),
          signal: controller.signal,
        });

        if (!response.ok) return;

        const data = await response.json();
        lastSourceRef.current = { story: currentStory, resumeText: currentResume, sentenceCount: currentSentenceCount };
        setAnalysis(data);
        setAnswers(
          Object.fromEntries((data.missingFields || []).map((field) => [field.key, ""]))
        );
      } catch (err) {
        // Silently ignore aborts or network errors in background
      }
    }, 500);

    return () => {
      clearTimeout(timeoutId);
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentSentenceCount, resumeText, currentStep]);

  const groupedMissingFields = useMemo(() => {
    const groups = {
      critical: [],
      helpful: [],
    };

    for (const field of analysis?.missingFields || []) {
      const bucket = groups[field.priority] ? field.priority : "helpful";
      groups[bucket].push(field);
    }

    return [
      {
        key: "critical",
        title: "Career goals",
        description:
          "These questions help us understand what kind of work you want and what support would matter most.",
        fields: groups.critical,
      },
      {
        key: "helpful",
        title: "Life details",
        description:
          "These questions help us shape support around your schedule, your home life, and your current season.",
        fields: groups.helpful,
      },
    ].filter((group) => group.fields.length > 0);
  }, [analysis]);

  useEffect(() => {
    if (!groupedMissingFields.length) {
      return;
    }

    const exists = groupedMissingFields.some((group) => group.key === activeQuestionTab);
    if (!exists) {
      setActiveQuestionTab(groupedMissingFields[0].key);
    }
  }, [groupedMissingFields, activeQuestionTab]);

  const overview = useMemo(
    () => mergeOverview(analysis?.extracted, answers, formattedAnswers),
    [analysis, answers, formattedAnswers],
  );

  const summaryCounts = useMemo(() => {
    if (!overview) {
      return { filled: 0, missing: 0 };
    }

    let filled = 0;
    let missing = 0;
    for (const value of Object.values(overview)) {
      if (value === null || value === undefined || value === "") {
        missing += 1;
      } else {
        filled += 1;
      }
    }
    return { filled, missing };
  }, [overview]);

  const answeredCount = useMemo(
    () => Object.values(answers).filter((value) => value && (Array.isArray(value) ? value.length > 0 : String(value).trim())).length,
    [answers],
  );

  const exportSource = overview || finalPayload?.final;
  const conversation = useMemo(
    () => buildConversation(currentStep, analysis, groupedMissingFields, activeQuestionTab),
    [currentStep, analysis, groupedMissingFields, activeQuestionTab],
  );

  useEffect(() => {
    if (analysis) {
      setSaveState("idle");
    }
  }, [answers, analysis]);

  function canAccessStep(stepId) {
    if (stepId === 1) return true;
    if (stepId === 2) return Boolean(analysis);
    if (stepId === 3) return Boolean(finalPayload);
    return false;
  }

  async function handleAnalyze(event) {
    event.preventDefault();
    if (loading) return;

    const currentStory = story.trim();
    const currentResume = resumeText.trim();

    // If we've already parsed the exact same text in the background, skip fetching
    if (
      analysis &&
      lastSourceRef.current.story === currentStory &&
      lastSourceRef.current.resumeText === currentResume
    ) {
      setCurrentStep(2);
      return;
    }

    setLoading(true);
    setError("");
    setFinalPayload(null);
    setSaveState("idle");

    try {
      const response = await fetch(`${API_BASE}/api/intake/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ story, resumeText }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "We couldn't read that just yet.");
      }
      
      lastSourceRef.current = { story: currentStory, resumeText: currentResume, sentenceCount: (currentStory.match(/[.!?\n]+/g) || []).length };
      setAnalysis(data);
      setFinalPayload(null);
      setAnswers(
        Object.fromEntries((data.missingFields || []).map((field) => [field.key, ""])),
      );
      setCurrentStep(2);
    } catch (err) {
      setError(err.message);
      setAnalysis(null);
    } finally {
      setLoading(false);
    }
  }

  async function handleFinalize() {
    if (!overview) {
      return;
    }

    setLoading(true);
    setError("");
    setSaveState("saving");

    try {
      const response = await fetch(`${API_BASE}/api/intake/complete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          extracted: overview,
          answers: {},
        }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "We couldn't save this right now.");
      }
      setFinalPayload(data);
      setSaveState("saved");
    } catch (err) {
      setSaveState("error");
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function handleGoToJson() {
    if (finalPayload) {
      setCurrentStep(3);
    }
  }

  async function handleLoadSample() {
    setSampleLoading(true);
    setError("");

    try {
      const response = await fetch(`${API_BASE}/api/intake/sample`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "We couldn't create a sample story right now.");
      }
      setStory(data.story || "");
      setFinalPayload(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setSampleLoading(false);
    }
  }

  async function handleLoadSampleAnswers() {
    if (!analysis?.sourceText || !analysis?.missingFields?.length) {
      return;
    }

    setSampleAnswersLoading(true);
    setError("");

    try {
      const response = await fetch(`${API_BASE}/api/intake/sample-answers`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          story: analysis.story,
          sourceText: analysis.sourceText,
          missingFields: analysis.missingFields,
        }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "We couldn't create sample answers right now.");
      }
      setAnswers((current) => ({
        ...current,
        ...(data.answers || {}),
      }));
      setFinalPayload(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setSampleAnswersLoading(false);
    }
  }

  async function handleBlur(key, value) {
    if (!value || typeof value !== "string" || !value.trim()) return;
    try {
      const response = await fetch(`${API_BASE}/api/intake/normalize-answer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key, value, context: analysis?.sourceText || story }),
      });
      const data = await response.json();
      if (response.ok && data.normalized) {
        setFormattedAnswers((current) => ({
          ...current,
          [key]: data.normalized,
        }));
      }
    } catch (err) {
      console.warn("Failed to normalize", key, err);
    }
  }

  function handleReset() {
    setStory("");
    setResumeText("");
    setResumeFileName("");
    setResumeError("");
    setAnalysis(null);
    setAnswers({});
    setFormattedAnswers({});
    setFinalPayload(null);
    setError("");
    setCurrentStep(1);
    setSaveState("idle");
    setActiveQuestionTab("critical");
  }

  async function handleResumeUpload(event) {
    const [file] = Array.from(event.target.files || []);
    event.target.value = "";
    setResumeError("");

    if (!file) {
      return;
    }

    const extension = extensionForFile(file.name);
    if (!ACCEPTED_RESUME_EXTENSIONS.includes(extension)) {
      setResumeError("Upload a .pdf, .txt, .md, or .rtf resume.");
      return;
    }

    try {
      const parsedText =
        extension === ".pdf"
          ? await extractPdfText(file)
          : normalizeResumeText(await file.text(), file.name);

      if (!parsedText) {
        throw new Error(
          extension === ".pdf"
            ? "That PDF did not contain readable text. It may be image-only."
            : "That file did not contain readable text.",
        );
      }

      setResumeText(parsedText);
      setResumeFileName(file.name);
      setFinalPayload(null);
    } catch (err) {
      setResumeText("");
      setResumeFileName("");
      setResumeError(err.message || "We couldn't read that resume file.");
    }
  }

  function handleClearResume() {
    setResumeText("");
    setResumeFileName("");
    setResumeError("");
    setFinalPayload(null);
  }

  function renderStepPanel() {
    if (currentStep === 1) {
      return (
        <form className="composer" onSubmit={handleAnalyze}>
          <div className="composer-tools">
            <button className="link-button" disabled={sampleLoading} onClick={handleLoadSample} type="button">
              {sampleLoading ? "Loading random story..." : "Generate random story"}
            </button>
            <button className="link-button" onClick={handleReset} type="button">
              Clear
            </button>
          </div>

          <label className="sr-only" htmlFor="story">
            Your story
          </label>
          <textarea
            id="story"
            className="story-input"
            value={story}
            onChange={(event) => setStory(event.target.value)}
            placeholder="Describe your goals, your experience, and any challenges you’re facing. You can also upload a text resume below."
            rows={11}
          />

          <section className="resume-card">
            <div className="resume-card-head">
              <div>
                <p className="question-meta">Resume upload</p>
                <p className="hint-text">Upload a `.pdf`, `.txt`, `.md`, or `.rtf` resume to prefill more of the JSON.</p>
              </div>
              <label className="ghost-button file-button" htmlFor="resume-upload">
                Upload resume
              </label>
            </div>
            <input
              id="resume-upload"
              className="sr-only"
              accept=".pdf,.txt,.md,.rtf,application/pdf,text/plain,text/markdown,application/rtf"
              onChange={handleResumeUpload}
              type="file"
            />
            {resumeFileName ? (
              <div className="resume-preview">
                <div className="resume-preview-head">
                  <strong>{resumeFileName}</strong>
                  <button className="link-button" onClick={handleClearResume} type="button">
                    Remove
                  </button>
                </div>
              </div>
            ) : null}
            {resumeError ? <p className="resume-error">{resumeError}</p> : null}
          </section>

          <div className="composer-footer">
            <button className="primary-button" disabled={loading || (!story.trim() && !resumeText.trim())} type="submit">
              {loading ? "Building your overview..." : "Create overview"}
            </button>
          </div>
        </form>
      );
    }

    if (currentStep === 2) {
      const activeGroup =
        groupedMissingFields.find((group) => group.key === activeQuestionTab) ||
        groupedMissingFields[0];

      if (!analysis?.missingFields?.length) {
        return (
          <div className="finish-block">
            <p className="empty-state">
              All required information is filled. You can save this now.
            </p>
            <div className="button-row">
              <button className="primary-button" disabled={loading} onClick={handleFinalize} type="button">
                {loading ? "Saving..." : saveState === "saved" ? "Saved" : "Save"}
              </button>
              {finalPayload ? (
                <button className="action-link" onClick={handleGoToJson} type="button">
                  View JSON
                </button>
              ) : null}
            </div>
          </div>
        );
      }

      return (
        <>
          <div className="category-tabs" role="tablist" aria-label="Question categories">
            {groupedMissingFields.map((group) => (
              <button
                key={group.key}
                className={`category-tab ${activeQuestionTab === group.key ? "category-tab-active" : ""}`}
                onClick={() => setActiveQuestionTab(group.key)}
                role="tab"
                type="button"
              >
                <span>{group.title}</span>
                <strong>{group.fields.length}</strong>
              </button>
            ))}
          </div>

          <div className="composer-tools composer-tools-inline">
            <button
              className="link-button"
              disabled={sampleAnswersLoading}
              onClick={handleLoadSampleAnswers}
              type="button"
            >
              {sampleAnswersLoading ? "Loading sample answers..." : "Use sample answers"}
            </button>
          </div>

          {activeGroup ? (
            <div className="question-thread">
              {activeGroup.fields.map((field) => (
                <div className="question-turn" key={field.key}>
                  <div className="bubble bubble-guide">
                    <p className="question-meta">{fieldLabel(field.key)}</p>
                    <p>{simplifyQuestion(field.question, field.key)}</p>
                  </div>
                  <div className="answer-row">
                    <input
                      id={field.key}
                      className="answer-input"
                      type="text"
                      value={answers[field.key] || ""}
                      onChange={(event) => {
                        setAnswers((current) => ({
                          ...current,
                          [field.key]: event.target.value,
                        }));
                        setFormattedAnswers((current) => {
                          const next = { ...current };
                          delete next[field.key];
                          return next;
                        });
                      }}
                      onBlur={(event) => handleBlur(field.key, event.target.value)}
                      placeholder="Type your answer here"
                    />
                  </div>
                </div>
              ))}
            </div>
          ) : null}

          <div className="composer-footer composer-footer-actions">
            <div className="save-state-wrap">
              <p className="hint-text">{answeredCount} answers added.</p>
              <span className={`save-badge save-${saveState}`}>
                {saveState === "saving"
                  ? "Saving..."
                  : saveState === "saved"
                    ? "Saved"
                    : saveState === "error"
                      ? "Save failed"
                      : "Not saved yet"}
              </span>
            </div>
            <div className="button-row">
              <button
                className={`primary-button ${saveState === "saved" ? "primary-button-saved" : ""}`}
                disabled={loading}
                onClick={handleFinalize}
                type="button"
              >
                {loading ? "Saving..." : saveState === "saved" ? "Saved" : "Save intake"}
              </button>
              {finalPayload ? (
                <button className="action-link" onClick={handleGoToJson} type="button">
                  Go to JSON
                </button>
              ) : null}
            </div>
          </div>
        </>
      );
    }

return (
  <div className="finish-block">
    <pre className="json-block">
      <code>{JSON.stringify(exportSource || {}, null, 2)}</code>
    </pre>

    <div className="button-row">
      <button className="ghost-button" onClick={handleReset} type="button">
        Start over
      </button>
    </div>
  </div>
);
  }

  return (
    <main className="shell">
      <section className="workspace">
        <aside className="progress-rail" aria-label="Progress">
          <div className="progress-line" />
          {STEPS.map((step) => {
            const active = currentStep === step.id;
            const complete = currentStep > step.id;
            const available = canAccessStep(step.id);

            return (
              <button
                key={step.id}
                className={`progress-step ${active ? "progress-step-active" : ""} ${
                  complete ? "progress-step-complete" : ""
                }`}
                disabled={!available}
                onClick={() => available && setCurrentStep(step.id)}
                type="button"
              >
                <span className="progress-dot" />
                <span className="progress-copy">
                  <strong>{step.label}</strong>
                  <span>{step.note}</span>
                </span>
              </button>
            );
          })}
        </aside>

        <section className="conversation-panel">
          <header className="conversation-header">
            <div>
              <h1>
                {currentStep === 1 ? "Your story" : currentStep === 2 ? "More details" : "Your JSON"}
              </h1>
            </div>
          </header>

          <div className="conversation-stream">
            {conversation.map((message, index) => (
              <div className="message-row" key={`${message.title}-${index}`}>
                <div className="bubble bubble-guide">
                  <p className="question-meta">{message.title}</p>
                  <p>{message.body}</p>
                </div>
              </div>
            ))}

            <div className="message-row message-row-user">
              <div className="bubble bubble-user">{renderStepPanel()}</div>
            </div>

            {error ? (
              <div className="message-row">
                <div className="bubble bubble-error">{error}</div>
              </div>
            ) : null}
          </div>
        </section>

        <aside className="overview-panel">
          <div className="overview-head">
            <div>
              <h2>Your overview</h2>
            </div>
            {overview ? <span className="count-pill">{summaryCounts.filled} filled</span> : null}
          </div>

          {!overview ? (
            <p className="empty-state">
              Your overview will appear here.
            </p>
          ) : (
            <>
              <div className="overview-meta">
                <span className="meta-chip meta-chip-good">{summaryCounts.filled} ready</span>
                <span className="meta-chip meta-chip-soft">{summaryCounts.missing} still open</span>
              </div>

              <div className="overview-list">
                {Object.entries(overview).map(([key, value]) => {
                  const listItems = parseAsList(value, key);
                  const isMissing = value === null || value === undefined || value === "" || (Array.isArray(value) && value.length === 0);

                  if (currentStep === 1 && isMissing) {
                    return null;
                  }

                  return (
                    <article
                      className={`overview-item ${isMissing ? "overview-item-missing" : ""}`}
                      key={key}
                    >
                      <p className="field-key">{fieldLabel(key)}</p>
                      {listItems ? (
                        <div className="chip-list">
                          {listItems.map((v, i) => (
                            <span className="chip" key={i}>{String(v)}</span>
                          ))}
                        </div>
                      ) : (
                        <p className="field-value">{valueLabel(value)}</p>
                      )}
                    </article>
                  );
                })}
              </div>
            </>
          )}
        </aside>
      </section>
    </main>
  );
}

export default App;
