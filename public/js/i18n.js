(function() {
  var STRINGS = {
    'zh': {
      'lang_name': '简体中文',
      'loading': '处理中...',
      'network_error': '网络请求失败，请检查网络连接',
      'server_error': '服务器返回数据异常',
      'login_required': '请先登录',
      'send_code': '发送验证码到邮箱',
      'code_placeholder': '输入6位验证码',
      'search_placeholder': '搜索发件人或短信内容',
      'no_messages': '暂无短信',
      'load_more': '加载更多',
      'confirm': '确定',
      'cancel': '取消',
      'copy': '复制',
      'copied': '已复制到剪贴板',
      'delete': '删除',
      'delete_confirm': '确定删除此短信？此操作不可撤销。',
      'deleted': '已删除',
      'mark_read': '标为已读',
      'mark_unread': '标为未读',
      'mark_all_read': '全部标为已读',
      'no_unread': '没有未读短信',
      'export': '导出短信',
      'search': '搜索',
      'clear': '清除',
      'settings': '设置',
      'theme_settings': '主题设置',
      'account_info': '账号信息',
      'change_password': '修改密码',
      'change_pwd_email': '邮箱验证码改密',
      'switch_user': '切换用户',
      'change_server': '更换服务器',
      'logout': '退出登录',
      'about': '关于',
      'service_running': '服务运行中',
      'service_failed': '服务启动失败',
      'offline': '离线',
      'online': '在线',
      'history_tab': '历史',
      'read_tab': '已读',
      'unread_tab': '未读',
      'phone_label': '手机号',
      'email_label': '邮箱',
      'register_time': '注册时间',
      'last_login': '最后登录',
      'first_login': '首次登录',
      'new_sms': '新短信',
      'sms_count': '条',
      'server_addr': '服务器地址',
      'change_server_confirm': '修改后将断开当前连接，返回首页重新连接新服务器。',
      'logout_confirm': '清除所有本地数据，完全退出到初始页。',
      'switch_user_confirm': '退出当前账号，跳转到登录页。',
    },
    'zh-tw': {
      'lang_name': '繁體中文',
      'loading': '處理中...',
      'network_error': '網路請求失敗，請檢查網路連接',
      'server_error': '伺服器返回資料異常',
      'login_required': '請先登入',
      'send_code': '發送驗證碼到信箱',
      'code_placeholder': '輸入6位驗證碼',
      'search_placeholder': '搜尋寄件人或簡訊內容',
      'no_messages': '暫無簡訊',
      'load_more': '載入更多',
      'confirm': '確定',
      'cancel': '取消',
      'copy': '複製',
      'copied': '已複製到剪貼簿',
      'delete': '刪除',
      'delete_confirm': '確定刪除此簡訊？此操作不可撤銷。',
      'deleted': '已刪除',
      'mark_read': '標為已讀',
      'mark_unread': '標為未讀',
      'mark_all_read': '全部標為已讀',
      'no_unread': '沒有未讀簡訊',
      'export': '匯出簡訊',
      'search': '搜尋',
      'clear': '清除',
      'settings': '設定',
      'theme_settings': '主題設定',
      'account_info': '帳號資訊',
      'change_password': '修改密碼',
      'change_pwd_email': '信箱驗證碼改密',
      'switch_user': '切換用戶',
      'change_server': '更換伺服器',
      'logout': '退出登入',
      'about': '關於',
      'service_running': '服務運行中',
      'service_failed': '服務啟動失敗',
      'offline': '離線',
      'online': '在線',
      'history_tab': '歷史',
      'read_tab': '已讀',
      'unread_tab': '未讀',
      'phone_label': '手機號',
      'email_label': '信箱',
      'register_time': '註冊時間',
      'last_login': '最後登入',
      'first_login': '首次登入',
      'new_sms': '新簡訊',
      'sms_count': '條',
      'server_addr': '伺服器地址',
      'change_server_confirm': '修改後將斷開當前連接，返回首頁重新連接新伺服器。',
      'logout_confirm': '清除所有本地資料，完全退出到初始頁。',
      'switch_user_confirm': '退出當前帳號，跳轉到登入頁。',
    },
    'en': {
      'lang_name': 'English',
      'loading': 'Processing...',
      'network_error': 'Network request failed, please check your connection',
      'server_error': 'Server returned unexpected data',
      'login_required': 'Please login first',
      'send_code': 'Send code to email',
      'code_placeholder': 'Enter 6-digit code',
      'search_placeholder': 'Search sender or message content',
      'no_messages': 'No messages',
      'load_more': 'Load more',
      'confirm': 'OK',
      'cancel': 'Cancel',
      'copy': 'Copy',
      'copied': 'Copied to clipboard',
      'delete': 'Delete',
      'delete_confirm': 'Are you sure you want to delete this message? This cannot be undone.',
      'deleted': 'Deleted',
      'mark_read': 'Mark as read',
      'mark_unread': 'Mark as unread',
      'mark_all_read': 'Mark all as read',
      'no_unread': 'No unread messages',
      'export': 'Export messages',
      'search': 'Search',
      'clear': 'Clear',
      'settings': 'Settings',
      'theme_settings': 'Theme Settings',
      'account_info': 'Account Info',
      'change_password': 'Change Password',
      'change_pwd_email': 'Email Code Change Password',
      'switch_user': 'Switch User',
      'change_server': 'Change Server',
      'logout': 'Logout',
      'about': 'About',
      'service_running': 'Service is running',
      'service_failed': 'Service failed to start',
      'offline': 'Offline',
      'online': 'Online',
      'history_tab': 'History',
      'read_tab': 'Read',
      'unread_tab': 'Unread',
      'phone_label': 'Phone',
      'email_label': 'Email',
      'register_time': 'Registered',
      'last_login': 'Last Login',
      'first_login': 'First Login',
      'new_sms': 'New SMS',
      'sms_count': 'messages',
      'server_addr': 'Server Address',
      'change_server_confirm': 'This will disconnect the current connection and return to the home page.',
      'logout_confirm': 'Clear all local data and return to the initial page.',
      'switch_user_confirm': 'Logout current account and go to login page.',
    }
  };

  var _lang = localStorage.getItem('sms2web_lang') || 'zh';

  function tr(key) {
    var m = STRINGS[_lang] || STRINGS['zh'];
    return m[key] || key;
  }

  function setLang(code) {
    if (STRINGS[code]) {
      _lang = code;
      localStorage.setItem('sms2web_lang', code);
    }
  }

  function getLang() {
    return _lang;
  }

  function getLanguages() {
    var list = [];
    for (var code in STRINGS) {
      list.push({ code: code, name: STRINGS[code]['lang_name'] });
    }
    return list;
  }

  function applyLangToPage() {
    document.querySelectorAll('[data-i18n]').forEach(function(el) {
      el.textContent = tr(el.getAttribute('data-i18n'));
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(function(el) {
      el.placeholder = tr(el.getAttribute('data-i18n-placeholder'));
    });
    document.querySelectorAll('[data-i18n-title]').forEach(function(el) {
      el.title = tr(el.getAttribute('data-i18n-title'));
    });
    document.documentElement.lang = _lang === 'zh-tw' ? 'zh-TW' : (_lang === 'en' ? 'en' : 'zh-CN');
  }

  window.i18n = { tr: tr, setLang: setLang, getLang: getLang, getLanguages: getLanguages, applyLangToPage: applyLangToPage };
})();
