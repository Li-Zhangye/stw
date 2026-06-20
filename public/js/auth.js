function escHtml(s) {
  if (s === null || s === undefined) return '';
  const d = document.createElement('div');
  d.appendChild(document.createTextNode(String(s)));
  return d.innerHTML;
}

function escJs(s) {
    if (s === null || s === undefined) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/\n/g, '\\n').replace(/\r/g, '\\r');
}

function showMessage(element, type, text) {
  element.className = 'message ' + type;
  element.textContent = text;
  element.style.display = 'block';
}

function hideMessage(element) {
  element.style.display = 'none';
  element.className = 'message';
}

function setLoading(btn, isLoading) {
  if (isLoading) {
    btn.disabled = true;
    btn.innerHTML = '<span class="loading"></span>处理中...';
  } else {
    btn.disabled = false;
    btn.textContent = btn.getAttribute('data-original-text') || btn.textContent.replace('处理中...', '').trim();
  }
}

function apiPost(url, data, onSuccess, onError) {
  const xhr = new XMLHttpRequest();
  xhr.open('POST', url, true);
  xhr.setRequestHeader('Content-Type', 'application/json');
  xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');

  xhr.onreadystatechange = function () {
    if (xhr.readyState === 4) {
      const responseText = xhr.responseText;
      try {
        const result = JSON.parse(responseText);
        if (result.success) {
          if (onSuccess) onSuccess(result);
        } else {
          if (onError) onError(result);
        }
      } catch (e) {
        if (onError) onError({ success: false, message: '服务器返回数据异常' });
      }
    }
  };

  xhr.onerror = function () {
    if (onError) onError({ success: false, message: '网络请求失败，请检查网络连接' });
  };

  const jsonData = JSON.stringify(data);
  xhr.send(jsonData);
}
