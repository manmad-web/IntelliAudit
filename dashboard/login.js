'use strict';
const form = document.querySelector('#login');
const message = document.querySelector('#message');
async function session() { const response = await fetch('/api/auth/session', {credentials:'same-origin'}); if (!response.ok) throw new Error('The review service is unavailable. Please try again.'); return response.json(); }
function destination(user) { return user?.role === 'curator' ? '/admin.html' : '/'; }
session().then(data => { if (!data.hosted || data.authenticated) location.replace(destination(data.reviewer)); }).catch(error => { message.textContent = error.message; });
form.addEventListener('submit', async event => {
  event.preventDefault(); const button = form.querySelector('button'); button.disabled = true; message.textContent = 'Signing in…';
  try { const response = await fetch('/api/auth/login', {method:'POST', credentials:'same-origin', headers:{'Content-Type':'application/json'}, body:JSON.stringify({invite_code:form.elements.code.value.trim()})}); const data = await response.json(); if (!response.ok) throw new Error(data.error || 'Sign-in failed'); form.reset(); location.replace(destination(data.reviewer)); }
  catch (error) { message.textContent = error.message; button.disabled = false; }
});
