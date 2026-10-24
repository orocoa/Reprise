/* Render the bounded difflib JSON model. No diff algorithm or global listeners. */
(function (scope) {
  'use strict';
  const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const integer = value => Number.isSafeInteger(value) && value >= 0 ? value : 0;
  const lineNumber = value => Number.isSafeInteger(value) && value > 0 ? String(value) : '';
  const translations = {
    zh: {previous:'上一处变化',next:'下一处变化',changes:'处变化',inserted:'新增',deleted:'移除',lines:'行',
      unchanged:'两版文本相同。',unavailable:'此文件暂时不能逐行比较，仍可分别查看或取回完整文件。',
      binary:'此文件不是可比较的文本，仍可取回完整文件。',tooLarge:'文件较长、单行过长或重复内容较多，已暂停逐行比较，仍可分别查看或取回完整文件。',
      partial:'仅显示部分变化；下方结果不是完整比较。',inputTruncated:'读取到的文本不完整，未进行比较。请分别查看或取回完整文件。',
      gap:'未变内容',expand:'展开',omitted:'其余内容未展开；取回后可查看完整文件。',
      emptyAdded:'B 中新增了一个空文件。',emptyDeleted:'B 中移除了一个空文件。',
      eol:'换行',noEol:'行末无换行',legend:'− 仅在 A 中 · + 仅在 B 中',label:'逐行变化',
      a:'A 行号',b:'B 行号',content:'内容',location:'变化位置',readOnly:'比较不会更改原文件。'},
    en: {previous:'Previous change',next:'Next change',changes:'changes',inserted:'Added',deleted:'Removed',lines:'lines',
      unchanged:'The text is identical in both versions.',unavailable:'A line comparison is unavailable. You can still inspect or recover each complete file.',
      binary:'This file is not comparable text. You can still recover the complete file.',tooLarge:'The file is long, has very long lines, or has many repeated lines. Line comparison is paused; inspect or recover each complete file.',
      partial:'Only some changes are shown; this is not a complete comparison.',inputTruncated:'The supplied text is incomplete, so it was not compared. Inspect or recover the complete files.',
      gap:'unchanged lines',expand:'Show',omitted:'The remaining content is not shown. Recover the file to inspect it in full.',
      emptyAdded:'An empty file was added in B.',emptyDeleted:'An empty file was removed in B.',
      eol:'Line ending',noEol:'No newline at end of line',legend:'− Only in A · + Only in B',label:'Line changes',
      a:'A line',b:'B line',content:'Content',location:'Change position',readOnly:'Comparing does not change the original files.'}
  };

  function render(model, options = {}) {
    const language = options.language === 'en' ? 'en' : 'zh';
    const t = translations[language], d = model && typeof model === 'object' ? model : {};
    const summary = d.summary || {}, hunks = Array.isArray(d.hunks) ? d.hunks.slice(0, 2000) : [];
    const gaps = Array.isArray(d.gaps) ? d.gaps.slice(0, 2001) : [];
    let remaining = 2000;
    const seen = new Set();
    const rows = list => (Array.isArray(list) ? list : []).slice(0, remaining).map(row => {
      remaining--;
      const kind = ['insert','delete','equal'].includes(row.kind) ? row.kind : 'equal';
      const change = kind !== 'equal' && Number.isSafeInteger(row.change) && row.change >= 0 ? row.change : null;
      const anchor = change !== null && !seen.has(change);
      if (anchor) seen.add(change);
      const ending = ({lf:'LF',crlf:'CRLF',cr:'CR',none:''})[row.eol];
      const endingLabel = ending ? `${t.eol} (${ending})` : t.noEol;
      return `<div class="text-diff-row text-diff-${kind}" role="row"${anchor ? ' data-text-diff-change tabindex="-1"' : ''}><span class="text-diff-number" role="cell">${lineNumber(row.before_line)}</span><span class="text-diff-number" role="cell">${lineNumber(row.after_line)}</span><span class="text-diff-sign" aria-hidden="true">${kind === 'insert' ? '+' : kind === 'delete' ? '−' : ' '}</span><code role="cell" data-user-content>${escape(row.text)}${kind !== 'equal' ? `<span class="text-diff-ending" title="${escape(endingLabel)}" aria-label="${escape(endingLabel)}">${ending ? '↵ ' + ending : '∅'}</span>` : ''}</code></div>`;
    }).join('');
    // Match the server allocation: changed hunks have priority over gaps.
    const hunkMarkup = hunks.map(hunk => `<div class="text-diff-hunk">${rows(hunk.rows)}${hunk.omitted_rows ? `<p class="text-diff-notice">${escape(t.partial)}</p>` : ''}</div>`);
    const gapMarkup = new Map();
    gaps.forEach(gap => {
      const content = rows(gap.rows), index = integer(gap.before_hunk);
      const note = gap.omitted_rows ? `<p class="text-diff-notice">${escape(t.omitted)}</p>` : '';
      const label = language === 'en' ? `${t.expand} ${integer(gap.count)} ${t.gap}` : `${t.expand} ${integer(gap.count)} 行${t.gap}`;
      const html = content ? `<details class="text-diff-gap"><summary>${escape(label)}</summary>${content}${note}</details>` : `<div class="text-diff-gap-label">${escape(label.replace(t.expand, '').trim())}${note}</div>`;
      gapMarkup.set(index, (gapMarkup.get(index) || '') + html);
    });
    let message = '';
    if (d.reason === 'empty_added') message = t.emptyAdded;
    else if (d.reason === 'empty_deleted') message = t.emptyDeleted;
    else if (d.status === 'unchanged') message = t.unchanged;
    else if (d.status === 'too_large') message = t.tooLarge;
    else if (d.reason === 'input_truncated') message = t.inputTruncated;
    else if (d.status === 'truncated') message = t.partial;
    else if (!['ok','unchanged'].includes(d.status)) message = d.reason === 'binary' ? t.binary : t.unavailable;
    const changes = integer(summary.changes), disabled = seen.size ? '' : ' disabled';
    const countText = language === 'en' ? `${changes} ${t.changes} · ${t.inserted} ${integer(summary.inserted)} · ${t.deleted} ${integer(summary.deleted)}` : `${changes} ${t.changes} · ${t.inserted} ${integer(summary.inserted)} 行 · ${t.deleted} ${integer(summary.deleted)} 行`;
    const body = hunks.map((_, index) => (gapMarkup.get(index) || '') + hunkMarkup[index]).join('') + (gapMarkup.get(hunks.length) || '');
    const valid = ['ok','unchanged','truncated'].includes(d.status) && d.reason !== 'input_truncated';
    return `<section class="text-diff" data-text-diff-root data-text-diff-index="-1" aria-label="${escape(t.label)}">${message ? `<p class="text-diff-notice" role="status">${escape(message)}</p>` : ''}${valid ? `<div class="text-diff-toolbar"><p>${escape(countText)}</p><div class="text-diff-navigation"><button type="button" class="secondary-button" data-text-diff-action="previous"${disabled}>${escape(t.previous)}</button><span data-text-diff-position role="status" aria-label="${escape(t.location)}">0 / ${seen.size}</span><button type="button" class="secondary-button" data-text-diff-action="next"${disabled}>${escape(t.next)}</button></div></div><p class="text-diff-legend">${escape(t.legend)}</p><div class="text-diff-lines" role="table" aria-label="${escape(t.label)}"><div class="text-diff-column-labels" role="row"><span role="columnheader">${escape(t.a)}</span><span role="columnheader">${escape(t.b)}</span><span aria-hidden="true"></span><span role="columnheader">${escape(t.content)}</span></div>${body}</div>` : ''}</section>`;
  }

  function handleAction(button, container) {
    const action = button?.dataset?.textDiffAction;
    if (!['previous','next'].includes(action)) return false;
    const root = button.closest?.('[data-text-diff-root]');
    if (!root || (container && container !== root && !container.contains(root))) return false;
    const targets = Array.from(root.querySelectorAll('[data-text-diff-change]'));
    if (!targets.length) return true;
    let index = Number(root.dataset.textDiffIndex);
    if (!Number.isInteger(index) || index < 0 || index >= targets.length) index = action === 'next' ? -1 : 0;
    index = (index + (action === 'next' ? 1 : -1) + targets.length) % targets.length;
    root.dataset.textDiffIndex = String(index);
    targets.forEach((target, number) => number === index ? target.setAttribute('aria-current', 'true') : target.removeAttribute('aria-current'));
    const target = targets[index];
    target.focus({preventScroll: true});
    target.scrollIntoView({block: 'nearest'});
    const position = root.querySelector('[data-text-diff-position]');
    if (position) position.textContent = `${index + 1} / ${targets.length}`;
    return true;
  }

  scope.RepriseTextDiff = Object.freeze({render, handleAction});
})(globalThis);
