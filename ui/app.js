const form = document.querySelector('#tailor-form');
const jd = document.querySelector('#jd');
const status = document.querySelector('#status');
const generate = document.querySelector('#generate');
const tabs = [...document.querySelectorAll('[data-tab]')];
let hasResults = false;
let currentPayload = null;

jd.addEventListener('input', () => { document.querySelector('#char-count').textContent = `${jd.value.length.toLocaleString()} characters`; });
function showTab(name) {
  tabs.forEach(tab => {
    const active = tab.dataset.tab === name;
    tab.setAttribute('aria-selected', String(active));
    tab.tabIndex = active ? 0 : -1;
    document.getElementById(tab.dataset.tab).hidden = !active || !hasResults;
  });
}
tabs.forEach((tab, index) => {
  tab.addEventListener('click', () => showTab(tab.dataset.tab));
  tab.addEventListener('keydown', event => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    let next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
    tabs[next].focus(); showTab(tabs[next].dataset.tab);
  });
});
function el(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}
function display(data) {
  hasResults = true;
  document.querySelector('#empty').hidden = true;
  document.querySelector('#results').hidden = false;
  document.querySelector('#fit').textContent = `${data.score.candidate_jd_fit}/100`;
  const visibility = data.skill_visibility;
  document.querySelector('#visibility').textContent = visibility.total ? `${visibility.before}/${visibility.total} → ${visibility.after}/${visibility.total}` : 'No supported skills';
  document.querySelector('#assessment').textContent = data.score.application_assessment;
  document.querySelector('#facts').textContent = `${data.fact_count} / ${data.fact_count}`;
  document.querySelector('#state-pill').textContent = 'Review required';
  const choices = document.querySelector('#skill-options'); choices.replaceChildren();
  for (const item of data.skill_options) {
    const label = el('label', undefined, 'skill-choice');
    const checkbox = document.createElement('input'); checkbox.type = 'checkbox'; checkbox.value = item.key; checkbox.checked = Object.hasOwn(currentPayload, 'selected_skills') ? data.selected_skills.includes(item.key) : true;
    const copy = el('span'); copy.append(el('strong', item.label), el('small', `${item.action === 'highlight' ? 'Highlight existing skill' : 'Add to skills list'} · ${item.context} · Evidence: ${item.evidence_ids.join(', ')}`));
    label.append(checkbox, copy); choices.append(label);
  }
  document.querySelector('#apply-skills').disabled = !data.skill_options.length;
  document.querySelector('#skill-action-hint').textContent = data.skill_options.length ? `${data.skill_options.length} supported skills available. Customize selections in Evidence & gaps. Candidate fit stays the same.` : 'No additional supported skill actions found. Missing skills require new evidence.';
  const appliedHighlights = data.skill_options.filter(item => item.action === 'highlight' && data.selected_skills.includes(item.key)).length;
  const appliedAdditions = data.skill_options.filter(item => item.action === 'add' && data.selected_skills.includes(item.key)).length;
  document.querySelector('#skill-message').textContent = data.selected_skills.length ? `Highlighted ${appliedHighlights} existing skills; added ${appliedAdditions} supported skill${appliedAdditions === 1 ? '' : 's'}. JD skills shown in Skills: ${visibility.before}/${visibility.total} → ${visibility.after}/${visibility.total}. Candidate fit unchanged.` : '';
  document.querySelector('#renderer-note').textContent = `${data.validation.renderer}. ${data.validation.compilation.status === 'passed' ? 'LaTeX compiled.' : 'LaTeX PDF export unavailable; showing a layout preview.'} PDF checks: ${data.validation.pdf.status || 'unexecuted'}. Evidence coverage is a provisional term-based measure, not a hiring probability.`;
  document.querySelector('#pdf-image').src = data.downloads['preview.png'];
  document.querySelector('#open-pdf').href = data.downloads['resume.pdf'];
  for (const [id, file] of [['download-pdf','resume.pdf'],['download-tex','resume.tex'],['download-report','score_report.md'],['download-changes','resume_changes.md']]) document.getElementById(id).href = data.downloads[file];
  for (const [file, id] of [['resume.pdf', 'download-pdf'], ['resume.tex', 'download-tex']]) document.getElementById(id).download = data.download_names[file];
  const changes = document.querySelector('#changes-list'); changes.replaceChildren();
  document.querySelector('#change-count').textContent = data.changes.length;
  if (!data.changes.length) changes.append(el('p', 'The original ordering already fits this JD. No ordering changes were needed.', 'change-section'));
  for (const change of data.changes) {
    const section = el('section', undefined, 'change-section'); section.append(el('h4', change.section));
    change.after.forEach((id, index) => {
      const previous = change.before.indexOf(id);
      if (previous === index) return;
      const row = el('div', undefined, 'change-item');
      row.append(el('span', `${previous + 1} → ${index + 1}`, 'position'), el('span', change.labels[id])); section.append(row);
    }); changes.append(section);
  }
  const applied = data.skill_options.filter(item => data.selected_skills.includes(item.key));
  document.querySelector('#change-count').textContent = data.changes.length + (applied.length ? 1 : 0);
  if (applied.length) {
    const section = el('section', undefined, 'change-section'); section.append(el('h4', 'Skills added and highlighted'));
    for (const item of applied) section.append(el('p', `${item.label}: ${item.action === 'highlight' ? 'highlighted in existing skills' : 'added to skills list'}. Evidence: ${item.evidence_ids.join(', ')} (${item.context}).`, 'change-item'));
    changes.append(section);
  }
  const mapping = document.querySelector('#mapping-list'); mapping.replaceChildren();
  for (const item of data.mapping) {
    const section = el('section', undefined, 'requirement');
    const top = el('div', undefined, 'requirement-top');
    top.append(el('strong', item.canonical.replaceAll('_', ' ')), el('span', item.classification, `badge ${item.classification}`));
    section.append(top, el('p', item.original_text), el('p', item.reason), el('small', `Evidence: ${item.evidence_ids.join(', ') || 'No matching evidence'} · ${item.status}`)); mapping.append(section);
  }
  const warnings = document.querySelector('#master-warnings'); warnings.replaceChildren(el('strong', 'Master facts to review'));
  data.validation.unresolved_master_items.forEach(item => warnings.append(el('p', item.detail)));
  showTab('preview');
}
form.addEventListener('submit', async event => {
  event.preventDefault();
  await generateResume(Object.fromEntries(new FormData(form)));
});
document.querySelector('#apply-skills').addEventListener('click', async () => {
  if (!currentPayload) return;
  const selected = [...document.querySelectorAll('#skill-options input:checked')].map(input => input.value);
  await generateResume({...currentPayload, selected_skills: selected});
});
async function generateResume(payload) {
  generate.disabled = true; generate.textContent = 'Generating your resume…';
  document.querySelector('#apply-skills').disabled = true;
  status.className = ''; status.textContent = 'Matching requirements, prioritizing evidence, and rendering your preview…';
  try {
    const response = await fetch('/api/tailor', {
      method: 'POST', headers: {'Content-Type':'application/json', 'X-Resume-Token':document.querySelector('meta[name=resume-token]').content},
      body: JSON.stringify(payload)
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Generation failed');
    currentPayload = payload;
    display(data); status.textContent = 'Your resume is ready for review. All master facts retained.';
  } catch (error) { status.className = 'error'; status.textContent = error.message; }
  finally { generate.disabled = false; generate.textContent = 'Tailor my resume ↗'; if (hasResults) document.querySelector('#apply-skills').disabled = !document.querySelector('#skill-options input'); }
}
showTab('preview');

const uploadStatus = document.querySelector('#upload-status');
const resumeText = document.querySelector('#resume-text');
let detectedLinks = [];
let editorTouched = false;
let savedBoldPhrases = [];
const boldPhrases = text => [...text.matchAll(/\*\*(.*?)\*\*/g)].map(match => match[1]);
resumeText.addEventListener('input', () => { editorTouched = true; });
async function resumeApi(path, payload) {
  const response = await fetch(path, {method: 'POST', headers: {'Content-Type':'application/json', 'X-Resume-Token':document.querySelector('meta[name=resume-token]').content}, body:JSON.stringify(payload)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Resume import failed');
  return data;
}
function profileReady(data, afterSave = false) {
  if (data.review_text && (afterSave || !editorTouched)) resumeText.value = data.review_text;
  savedBoldPhrases = afterSave || !editorTouched ? boldPhrases(data.review_text || '') : [];
  document.querySelector('#profile-name').textContent = data.name || 'Upload your resume';
  document.querySelector('#profile-summary').textContent = data.name ? 'Local profile connected' : 'No profile connected';
  document.querySelector('#master-summary').textContent = data.name ? `${data.fact_count} reviewed claims · ${data.link_count} clickable links · ${data.emphasis_count} bold phrases` : 'Upload a resume to begin';
  generate.disabled = !data.name;
  status.textContent = data.name ? 'Resume connected. Enter a target role and JD to tailor.' : 'Upload and save your reviewed resume above to enable tailoring.';
}
document.querySelector('#use-example').addEventListener('click', async () => {
  detectedLinks = [];
  editorTouched = true;
  resumeText.value = await (await fetch('/resume-format.txt')).text();
  uploadStatus.textContent = 'Example loaded. Replace all sample details before saving.';
});
document.querySelector('#resume-file').addEventListener('change', async event => {
  const file = event.target.files[0];
  if (!file) return;
  const selection = document.querySelector('#file-selection');
  selection.textContent = `${file.name} · ${file.size < 1024 * 1024 ? `${Math.max(1, Math.round(file.size / 1024))} KB` : `${(file.size / (1024 * 1024)).toFixed(1)} MB`}`;
  selection.classList.add('has-file');
  const save = document.querySelector('#save-resume'); save.disabled = true;
  try {
    if (file.size > 5 * 1024 * 1024) throw new Error('Maximum upload size is 5 MB');
    editorTouched = true;
    uploadStatus.textContent = 'Reading resume...';
    if (file.name.toLowerCase().endsWith('.txt')) {
      detectedLinks = [];
      resumeText.value = new TextDecoder('utf-8', {fatal:true}).decode(await file.arrayBuffer());
    } else if (file.name.toLowerCase().endsWith('.pdf')) {
      const bytes = new Uint8Array(await file.arrayBuffer()); let binary = '';
      for (let i=0; i<bytes.length; i+=8192) binary += String.fromCharCode(...bytes.subarray(i,i+8192));
      const extracted = await resumeApi('/api/extract', {data:btoa(binary)});
      detectedLinks = extracted.links;
      resumeText.value = extracted.text;
      resumeText.value = (await resumeApi('/api/prepare', {text:extracted.text, links:detectedLinks})).text;
    } else throw new Error('Choose a PDF or UTF-8 TXT file');
    uploadStatus.textContent = 'Review detected contact details, URLs, employer boundaries, and bullets below. Correct any missing fields, then save.';
  } catch (error) { importError(error); }
  finally { save.disabled = false; }
});
document.querySelector('#save-resume').addEventListener('click', async () => {
  const button = document.querySelector('#save-resume'); button.disabled = true;
  try {
    if (!/^Name:/mi.test(resumeText.value)) {
      await prepareText();
      return;
    }
    const currentBoldPhrases = boldPhrases(resumeText.value);
    const preserveEmphasis = savedBoldPhrases.every(phrase => currentBoldPhrases.includes(phrase));
    const data = await resumeApi('/api/resume', {text:resumeText.value, preserve_emphasis:preserveEmphasis});
    profileReady(data, true); status.textContent = 'Resume saved. Enter your target role and JD, then tailor.'; status.className = ''; hasResults = false; currentPayload = null;
    document.querySelector('#results').hidden = true; document.querySelector('#empty').hidden = false;
    document.querySelector('#state-pill').textContent = 'Awaiting JD';
    uploadStatus.textContent = `Saved ${data.fact_count} claims and ${data.emphasis_count} bold phrases locally. Enter a job description below.`;
  } catch (error) { importError(error); }
  finally { button.disabled = false; }
});
fetch('/api/profile').then(response => { if (!response.ok) throw new Error('Profile status unavailable'); return response.json(); }).then(profileReady).catch(error => { uploadStatus.textContent = error.message; });

function importError(error) {
  uploadStatus.textContent = error.message;
  uploadStatus.className = 'error';
  status.textContent = 'Resume import needs attention: ' + error.message;
  status.className = 'error';
  uploadStatus.scrollIntoView({behavior:'smooth', block:'center'});
}
async function prepareText() {
  const data = await resumeApi('/api/prepare', {text:resumeText.value, links:detectedLinks});
  resumeText.value = data.text;
  uploadStatus.className = '';
  uploadStatus.textContent = 'Draft prepared. Review contact fields and employer boundaries, then click Save reviewed resume.';
  resumeText.focus();
}
document.querySelector('#prepare-resume').addEventListener('click', async () => {
  try { await prepareText(); } catch (error) { importError(error); }
});
