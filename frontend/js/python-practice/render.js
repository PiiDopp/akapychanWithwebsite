// 題目畫面渲染
import { indentLines } from './helpers.js';
import { setCurrentQuestion, setOutput } from './dom.js';

export async function renderOneQuestion(host, data, idx, setId) {
  const list = Array.isArray(data?.coding_practice) ? data.coding_practice : [];
  const item = list[idx];
  if (!item) {
    setOutput(`找不到第 ${idx + 1} 題資料`);
    return;
  }

  const title = item.title ?? `題目 ${idx + 1}`;
  const desc = item.description ?? '';

  const titleEl = host.querySelector('.textContent .title');
  const descEl  = host.querySelector('.textContent .description');
  const expList = host.querySelector('.textContent .expContent');

  if (titleEl) titleEl.textContent = title;
  if (descEl)  descEl.textContent  = desc;

  if (expList) {
    expList.innerHTML = '';

    // Constraints
    if (typeof item.constraints === 'string' && item.constraints.trim()) {
      const cTitle = document.createElement('div');
      cTitle.className = 'constraintsTitle';
      cTitle.textContent = '# 限制（Constraints）';
      expList.appendChild(cTitle);

      const cBody = document.createElement('pre');
      cBody.className = 'constraintsBody';
      cBody.textContent = indentLines(item.constraints);
      expList.appendChild(cBody);
    }

    // Examples
    const ex = item.examples;
    const eTitle = document.createElement('div');
    eTitle.className = 'expTitle';
    eTitle.textContent = '# 範例（Examples）';
    expList.appendChild(eTitle);

    const examples = [];
    if (Array.isArray(ex)) {
      ex.forEach((e) => {
        if (e && (e.input != null || e.output != null)) {
          examples.push({
            input:  e.input  != null ? String(e.input)  : '',
            output: e.output != null ? String(e.output) : '',
          });
        }
      });
    } else if (ex && typeof ex === 'object' && (ex.input != null || ex.output != null)) {
      examples.push({
        input:  ex.input  != null ? String(ex.input)  : '',
        output: ex.output != null ? String(ex.output) : '',
      });
    }

    if (examples.length) {
      const ul = document.createElement('ul');
      ul.className = 'examples';
      examples.forEach((eg, i) => {
        const li = document.createElement('li');
        li.className = 'exampleItem';

        const head = document.createElement('div');
        head.className = 'exampleHead';
        head.textContent = `example ${i + 1}`;
        li.appendChild(head);

        const inWrap = document.createElement('div');
        inWrap.className = 'exampleBlock';
        const inLbl = document.createElement('div');
        inLbl.className = 'exampleLabel';
        inLbl.textContent = 'Input';
        const inPre = document.createElement('pre');
        inPre.className = 'exampleInput';
        inPre.textContent = indentLines(eg.input);
        inWrap.appendChild(inLbl);
        inWrap.appendChild(inPre);
        li.appendChild(inWrap);

        const outWrap = document.createElement('div');
        outWrap.className = 'exampleBlock';
        const outLbl = document.createElement('div');
        outLbl.className = 'exampleLabel';
        outLbl.textContent = 'Output';
        const outPre = document.createElement('pre');
        outPre.className = 'exampleOutput';
        outPre.textContent = indentLines(eg.output);
        outWrap.appendChild(outLbl);
        outWrap.appendChild(outPre);
        li.appendChild(outWrap);

        ul.appendChild(li);
      });
      expList.appendChild(ul);
    } else {
      const p = document.createElement('div');
      p.className = 'expEmpty';
      p.textContent = '（此題暫無提供範例）';
      expList.appendChild(p);
    }
  }
  setCurrentQuestion(setId, idx);
}