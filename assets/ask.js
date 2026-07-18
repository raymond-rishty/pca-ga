'use strict';

const copyButton = document.getElementById('copyPrompt');
const promptCode = document.querySelector('.ask-content pre code');
const toast = document.getElementById('copyToast');

async function copyPrompt() {
  if (!promptCode) return;
  const value = promptCode.textContent.trim();

  try {
    await navigator.clipboard.writeText(value);
  } catch (_) {
    const textarea = document.createElement('textarea');
    textarea.value = value;
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand('copy');
    textarea.remove();
  }

  copyButton.textContent = 'Copied';
  toast.classList.add('visible');
  window.setTimeout(() => {
    copyButton.textContent = 'Copy prompt';
    toast.classList.remove('visible');
  }, 1800);
}

copyButton?.addEventListener('click', copyPrompt);
