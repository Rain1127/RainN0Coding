const { createApp, computed, onMounted, reactive } = window.Vue;

const APP_BASE = "/api";
const APP_ROUTES = [
  { path: "/", label: "生成控制台", caption: "从需求直达代码", protected: true },
  { path: "/projects", label: "我的项目", caption: "查看和管理生成结果", protected: true },
  { path: "/history", label: "历史记录", caption: "回看最近会话与版本", protected: true },
  { path: "/templates", label: "模板 / 灵感", caption: "快速开始常见场景", protected: true },
  { path: "/settings", label: "设置", caption: "账号与偏好配置", protected: true },
  { path: "/login", label: "登录", caption: "账号密码登录", protected: false },
  { path: "/register", label: "注册", caption: "创建一个新账号", protected: false }
];

const QUICK_PROMPTS = [
  {
    title: "实时数据",
    detail: "销售汇总统计",
    prompt: "帮我做一个带图表、筛选条件和同比分析的销售数据统计看板。"
  },
  {
    title: "系统交互",
    detail: "关于手册",
    prompt: "请设计一个带搜索、目录导航和详情页的系统使用手册中心。"
  },
  {
    title: "业务系统",
    detail: "数据安全",
    prompt: "生成一个包含权限控制、访问审计和数据脱敏说明的业务系统首页。"
  }
];

const MODE_OPTIONS = [
  "深度思考",
  "知识检索",
  "多轮协作"
];

const TEMPLATE_GROUPS = [
  {
    name: "热门模板",
    items: [
      "SaaS 控制台",
      "AI 工作台",
      "企业门户",
      "内容管理台"
    ]
  },
  {
    name: "灵感方向",
    items: [
      "客服助手",
      "流程审批",
      "运营看板",
      "知识检索"
    ]
  }
];

const PROJECT_ITEMS = [
  { name: "智能工单系统", tag: "Vue 3 + Spring Boot", status: "最近更新于 2 小时前" },
  { name: "品牌官网生成器", tag: "HTML / CSS / JS", status: "最近更新于 昨天" },
  { name: "销售数据工作台", tag: "Vue 3 + ECharts", status: "最近更新于 3 天前" }
];

const HISTORY_ITEMS = [
  { title: "为智能工单系统补全权限页面", time: "今天 14:20", type: "继续生成" },
  { title: "创建品牌官网首页结构", time: "今天 11:08", type: "新建会话" },
  { title: "优化数据图表展示逻辑", time: "昨天 20:16", type: "迭代修改" }
];

const HOME_CONVERSATION_GROUPS = [
  {
    label: "今天",
    items: [
      "销售数据统计内容",
      "如何思考 AI 对于程序员的提升？",
      "数据加密实现思路和 SPI 含义",
      "数据加密实现方法",
      "RAG 对于 AI 来说有什么创新"
    ]
  },
  {
    label: "7天内",
    items: [
      "SPI 定义及应用场景",
      "苹果公司现在 CEO 及其年龄",
      "关于 AI 画图如何编写问题",
      "阿里云产品付费如何？"
    ]
  }
];

const HOME_UTILITY_LINKS = [
  { path: "/projects", label: "我的项目" },
  { path: "/history", label: "历史记录" },
  { path: "/templates", label: "模板灵感" },
  { path: "/settings", label: "偏好设置" }
];

function includesKeyword(source, keyword) {
  if (!keyword) {
    return true;
  }
  return source.toLowerCase().includes(keyword.trim().toLowerCase());
}

function stripBase(pathname) {
  if (!pathname.startsWith(APP_BASE)) {
    return pathname || "/";
  }
  const stripped = pathname.slice(APP_BASE.length) || "/";
  return stripped.startsWith("/") ? stripped : `/${stripped}`;
}

function normalizeRoute(route) {
  if (!route) {
    return "/";
  }
  return route.startsWith("/") ? route : `/${route}`;
}

function routeMeta(route) {
  return APP_ROUTES.find((item) => item.path === route) || null;
}

async function request(path, options = {}) {
  const response = await fetch(`${APP_BASE}${path}`, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    },
    ...options
  });

  const payload = await response.json().catch(() => ({
    code: -1,
    message: "服务返回了无法识别的数据"
  }));

  if (payload.code !== 0) {
    throw new Error(payload.message || "请求失败");
  }

  return payload.data;
}

createApp({
  setup() {
    const state = reactive({
      booting: true,
      route: normalizeRoute(stripBase(window.location.pathname)),
      user: null,
      loading: false,
      message: "",
      messageType: "info",
      selectedMode: MODE_OPTIONS[0],
      generationInput: "",
      sessionSearch: "",
      loginForm: {
        userAccount: "",
        userPassword: ""
      },
      registerForm: {
        userAccount: "",
        userPassword: "",
        checkPassword: ""
      }
    });

    const navItems = APP_ROUTES.filter((item) => item.protected);
    const authItems = APP_ROUTES.filter((item) => !item.protected);

    const activeRoute = computed(() => routeMeta(state.route));
    const isLoginPage = computed(() => state.route === "/login");
    const isRegisterPage = computed(() => state.route === "/register");
    const isProtectedPage = computed(() => activeRoute.value?.protected === true);
    const homeConversationGroups = computed(() =>
      HOME_CONVERSATION_GROUPS.map((group) => ({
        label: group.label,
        items: group.items.filter((item) => includesKeyword(item, state.sessionSearch))
      })).filter((group) => group.items.length > 0)
    );

    function setMessage(text, type = "info") {
      state.message = text;
      state.messageType = type;
    }

    function clearMessage() {
      state.message = "";
      state.messageType = "info";
    }

    function navigate(path, replace = false) {
      const nextRoute = normalizeRoute(path);
      const target = `${APP_BASE}${nextRoute === "/" ? "/" : nextRoute}`;
      if (replace) {
        window.history.replaceState({}, "", target);
      } else {
        window.history.pushState({}, "", target);
      }
      state.route = nextRoute;
      clearMessage();
    }

    function guardCurrentRoute() {
      const meta = routeMeta(state.route);

      if (!meta) {
        navigate(state.user ? "/" : "/login", true);
        return;
      }

      if (meta.protected && !state.user) {
        navigate("/login", true);
        return;
      }

      if (!meta.protected && state.user) {
        navigate("/", true);
      }
    }

    async function fetchCurrentUser() {
      try {
        state.user = await request("/user/get/login", {
          method: "GET",
          headers: {}
        });
      } catch (_error) {
        state.user = null;
      } finally {
        state.booting = false;
      }
    }

    async function submitLogin() {
      if (!state.loginForm.userAccount || !state.loginForm.userPassword) {
        setMessage("请输入账号和密码", "error");
        return;
      }

      state.loading = true;
      clearMessage();

      try {
        state.user = await request("/user/login", {
          method: "POST",
          body: JSON.stringify(state.loginForm)
        });
        setMessage("登录成功，欢迎回来", "success");
        navigate("/", true);
      } catch (error) {
        setMessage(error.message || "登录失败", "error");
      } finally {
        state.loading = false;
      }
    }

    async function submitRegister() {
      const { userAccount, userPassword, checkPassword } = state.registerForm;

      if (!userAccount || !userPassword || !checkPassword) {
        setMessage("请完整填写注册信息", "error");
        return;
      }

      if (userPassword !== checkPassword) {
        setMessage("两次输入的密码不一致", "error");
        return;
      }

      state.loading = true;
      clearMessage();

      try {
        await request("/user/register", {
          method: "POST",
          body: JSON.stringify(state.registerForm)
        });
        state.registerForm.userAccount = "";
        state.registerForm.userPassword = "";
        state.registerForm.checkPassword = "";
        setMessage("注册成功，请登录", "success");
        navigate("/login", true);
      } catch (error) {
        setMessage(error.message || "注册失败", "error");
      } finally {
        state.loading = false;
      }
    }

    async function logout() {
      state.loading = true;
      clearMessage();

      try {
        await request("/user/logout", {
          method: "POST"
        });
      } catch (_error) {
        // Ignore logout failure and continue returning to login.
      } finally {
        state.user = null;
        state.loading = false;
        navigate("/login", true);
      }
    }

    function closeOrBack() {
      if (window.history.length > 1) {
        window.history.back();
      } else {
        navigate("/login", true);
      }
    }

    function startNewGeneration() {
      state.generationInput = "";
      state.selectedMode = MODE_OPTIONS[0];
      navigate("/", false);
      setMessage("新的生成工作区已准备好", "success");
    }

    function pickPrompt(detail, title = "灵感卡片") {
      state.generationInput = detail;
      navigate("/", false);
      setMessage(`已将「${title}」填入输入区，你可以直接继续修改`, "info");
    }

    function continueConversation(title) {
      state.generationInput = `继续这个话题：${title}`;
      navigate("/", false);
      setMessage(`已切换到「${title}」的续写上下文`, "info");
    }

    function submitGeneration() {
      if (!state.generationInput.trim()) {
        setMessage("先输入你想生成的内容，再开始创建", "error");
        return;
      }
      setMessage("骨架阶段先完成产品外壳，后续会把真实生成链路接进来", "success");
    }

    window.addEventListener("popstate", () => {
      state.route = normalizeRoute(stripBase(window.location.pathname));
      guardCurrentRoute();
    });

    onMounted(async () => {
      await fetchCurrentUser();
      guardCurrentRoute();
    });

    return {
      state,
      navItems,
      authItems,
      MODE_OPTIONS,
      QUICK_PROMPTS,
      TEMPLATE_GROUPS,
      PROJECT_ITEMS,
      HISTORY_ITEMS,
      HOME_UTILITY_LINKS,
      activeRoute,
      homeConversationGroups,
      isLoginPage,
      isRegisterPage,
      isProtectedPage,
      navigate,
      submitLogin,
      submitRegister,
      logout,
      closeOrBack,
      startNewGeneration,
      pickPrompt,
      continueConversation,
      submitGeneration
    };
  },
  template: `
    <main v-if="state.booting" class="rewrite-loading">
      <section class="rewrite-loading__card">
        <div class="rewrite-loading__badge">AI CODE MOTHER</div>
        <h1 class="rewrite-loading__title">正在载入新的产品骨架</h1>
        <p class="rewrite-loading__copy">我们先确认登录状态，再切换到新的 AI 工作台。</p>
      </section>
    </main>

    <main v-else-if="!isProtectedPage" :class="['auth-shell', { 'auth-shell--register': isRegisterPage }]">
      <section :class="['auth-card', isRegisterPage ? 'auth-card--register' : 'auth-card--login']">
        <button class="auth-close" type="button" aria-label="返回上一页" @click="closeOrBack">×</button>
        <div class="auth-content">
          <div class="auth-main">
            <div class="auth-eyebrow">{{ isRegisterPage ? 'CREATE ACCOUNT' : 'AI CODE MOTHER' }}</div>
            <h1 class="auth-title">{{ isRegisterPage ? '注册账号，开始完整体验' : '登录以解锁更多功能' }}</h1>
            <p class="auth-subtitle">
              {{ isRegisterPage
                ? '创建一个新账号，后续即可保存项目、查看历史记录并继续生成代码。'
                : '使用账号密码登录，继续生成、预览和管理你的应用。' }}
            </p>

            <div v-if="state.message" :class="['auth-feedback', 'auth-feedback--' + state.messageType]">
              {{ state.message }}
            </div>

            <form v-if="isLoginPage" class="auth-form auth-form--native" @submit.prevent="submitLogin">
              <label class="auth-field">
                <span class="auth-field-label">账号</span>
                <input
                  v-model.trim="state.loginForm.userAccount"
                  class="auth-input"
                  type="text"
                  placeholder="请输入账号"
                  autocomplete="username"
                  maxlength="32"
                />
              </label>

              <label class="auth-field">
                <span class="auth-field-label">密码</span>
                <input
                  v-model="state.loginForm.userPassword"
                  class="auth-input"
                  type="password"
                  placeholder="请输入密码"
                  autocomplete="current-password"
                />
              </label>

              <label class="auth-checkbox">
                <input checked type="checkbox" disabled />
                <span class="auth-checkbox-text">
                  我已阅读并同意
                  <span class="auth-linkish">用户协议</span>
                  与
                  <span class="auth-linkish">隐私政策</span>
                </span>
              </label>

              <div class="auth-actions">
                <button class="auth-button auth-button--primary" type="submit" :disabled="state.loading">
                  {{ state.loading ? '登录中...' : '登 录' }}
                </button>
                <button class="auth-button auth-button--secondary" type="button" @click="navigate('/register')">
                  注册账号
                </button>
              </div>
              <div class="auth-caption">没有账号也没关系，先注册一个即可开始体验。</div>
            </form>

            <form v-else class="auth-form auth-form--native" @submit.prevent="submitRegister">
              <label class="auth-field">
                <span class="auth-field-label">账号</span>
                <input
                  v-model.trim="state.registerForm.userAccount"
                  class="auth-input"
                  type="text"
                  placeholder="请输入账号"
                  autocomplete="username"
                  maxlength="32"
                />
              </label>

              <label class="auth-field">
                <span class="auth-field-label">密码</span>
                <input
                  v-model="state.registerForm.userPassword"
                  class="auth-input"
                  type="password"
                  placeholder="请输入至少 8 位密码"
                  autocomplete="new-password"
                />
              </label>

              <label class="auth-field">
                <span class="auth-field-label">确认密码</span>
                <input
                  v-model="state.registerForm.checkPassword"
                  class="auth-input"
                  type="password"
                  placeholder="请再次输入密码"
                  autocomplete="new-password"
                />
              </label>

              <label class="auth-checkbox">
                <input checked type="checkbox" disabled />
                <span class="auth-checkbox-text">
                  我已阅读并同意
                  <span class="auth-linkish">用户协议</span>
                  与
                  <span class="auth-linkish">隐私政策</span>
                </span>
              </label>

              <div class="auth-actions">
                <button class="auth-button auth-button--primary" type="submit" :disabled="state.loading">
                  {{ state.loading ? '注册中...' : '注册账号' }}
                </button>
                <button class="auth-button auth-button--secondary" type="button" @click="navigate('/login')">
                  返回登录
                </button>
              </div>
              <div class="auth-caption">已有账号的话，也可以直接回到登录页完成进入。</div>
            </form>
          </div>

          <aside class="auth-aside">
            <div class="auth-symbol-cloud">
              <span class="auth-symbol auth-symbol--xl">(=^･ω･^=)</span>
              <span class="auth-symbol auth-symbol--lg auth-symbol--offset">૮ ˶ᵔ ᵕ ᵔ˶ ა</span>
              <span class="auth-symbol auth-symbol--md">✦ ﾟ +</span>
              <span class="auth-symbol auth-symbol--sm auth-symbol--right">₍ᐢ..ᐢ₎</span>
              <span class="auth-symbol auth-symbol--tiny">♡</span>
              <span class="auth-spark auth-spark--one"></span>
              <span class="auth-spark auth-spark--two"></span>
              <span class="auth-spark auth-spark--three"></span>
            </div>
            <div class="auth-face-grid">
              <span class="auth-face-pill">ヾ(•ω•\`)o</span>
              <span class="auth-face-pill">₊˚⊹♡</span>
              <span class="auth-face-pill">(｡•̀ᴗ-)✧</span>
              <span class="auth-face-pill">ฅ^•ﻌ•^ฅ</span>
            </div>
            <div class="auth-mini-row">
              <span class="auth-mini-pill">♪</span>
              <span class="auth-mini-pill">✿</span>
              <span class="auth-mini-pill">☘</span>
            </div>
          </aside>
        </div>
      </section>
    </main>

    <main v-else-if="state.route === '/'" class="rag-shell">
      <aside class="rag-sidebar">
        <div class="rag-sidebar__brand">
          <div class="rag-sidebar__brand-mark">AI</div>
          <div>
            <div class="rag-sidebar__brand-title">RAG 智能问答</div>
            <div class="rag-sidebar__brand-subtitle">Powered by AI</div>
          </div>
        </div>

        <section class="rag-starter-card">
          <div class="rag-starter-card__meta">
            <span>快速开始</span>
            <button type="button" class="rag-link-button" @click="navigate('/templates')">指南</button>
          </div>
          <button class="rag-starter-card__primary" type="button" @click="startNewGeneration">
            <span class="rag-plus-icon">+</span>
            <span>
              <strong>新建对话</strong>
              <small>从空白开始</small>
            </span>
          </button>
          <button class="rag-starter-card__secondary" type="button" @click="pickPrompt(QUICK_PROMPTS[2].prompt, QUICK_PROMPTS[2].title)">
            业务系统
          </button>
        </section>

        <section class="rag-search-card">
          <div class="rag-search-card__head">
            <span>搜索对话</span>
            <small>Ctrl / Cmd + K</small>
          </div>
          <label class="rag-search-box">
            <span>⌕</span>
            <input
              v-model.trim="state.sessionSearch"
              type="text"
              placeholder="搜索对话..."
            />
          </label>
        </section>

        <div class="rag-session-groups">
          <section v-for="group in homeConversationGroups" :key="group.label" class="rag-session-group">
            <h3>{{ group.label }}</h3>
            <button
              v-for="item in group.items"
              :key="item"
              type="button"
              class="rag-session-item"
              :class="{ 'is-active': state.generationInput.includes(item) }"
              @click="continueConversation(item)"
            >
              {{ item }}
            </button>
          </section>
        </div>

        <div class="rag-sidebar__footer">
          <nav class="rag-utility-nav">
            <button
              v-for="link in HOME_UTILITY_LINKS"
              :key="link.path"
              type="button"
              class="rag-utility-nav__item"
              @click="navigate(link.path)"
            >
              {{ link.label }}
            </button>
          </nav>

          <div class="rag-user-card">
            <div class="rag-user-card__avatar">{{ state.user?.userName?.slice(0, 1) || 'A' }}</div>
            <div class="rag-user-card__content">
              <strong>{{ state.user?.userName || state.user?.userAccount || 'admin' }}</strong>
              <span>{{ state.user?.userAccount || 'admin' }}</span>
            </div>
            <button class="rag-user-card__logout" type="button" :disabled="state.loading" @click="logout">
              {{ state.loading ? '退出中' : '退出' }}
            </button>
          </div>
        </div>
      </aside>

      <section class="rag-main">
        <header class="rag-topbar">
          <div class="rag-topbar__title">新对话</div>
          <div class="rag-topbar__actions">
            <button type="button" class="rag-topbar__ghost" @click="navigate('/history')">最近历史</button>
            <button type="button" class="rag-topbar__ghost" @click="navigate('/projects')">工作台</button>
          </div>
        </header>

        <div v-if="state.message" :class="['rag-banner', 'rag-banner--' + state.messageType]">
          {{ state.message }}
        </div>

        <section class="rag-hero">
          <div class="rag-hero__badge">RAG 智能问答</div>
          <h1>把问题变成<span>清晰答案</span></h1>
          <p>结构化提问、知识检索与深度思考，一次对话给出可执行方案。</p>

          <div class="rag-composer">
            <textarea
              v-model="state.generationInput"
              placeholder="输入需要深度分析的问题..."
            ></textarea>

            <div class="rag-composer__bottom">
              <div class="rag-mode-switches">
                <button
                  v-for="mode in MODE_OPTIONS"
                  :key="mode"
                  type="button"
                  :class="['rag-mode-chip', { 'is-active': state.selectedMode === mode }]"
                  @click="state.selectedMode = mode"
                >
                  {{ mode }}
                </button>
              </div>

              <button class="rag-send-button" type="button" @click="submitGeneration">发送</button>
            </div>
          </div>

          <div class="rag-helper-row">
            <span>深度思考模式已开启，AI 将进行更深入的分析推理</span>
          </div>

          <div class="rag-shortcut-row">
            <span>Enter 发送</span>
            <span>Shift + Enter 换行</span>
          </div>

          <div class="rag-divider">
            <span>试试这些开场</span>
          </div>

          <div class="rag-capability-grid">
            <button
              v-for="prompt in QUICK_PROMPTS"
              :key="prompt.title"
              type="button"
              class="rag-capability-card"
              @click="pickPrompt(prompt.prompt, prompt.title)"
            >
              <div class="rag-capability-card__icon">{{ prompt.title.slice(0, 1) }}</div>
              <div class="rag-capability-card__body">
                <strong>{{ prompt.title }}</strong>
                <small>{{ prompt.detail }}</small>
                <span>推荐问法：{{ prompt.prompt }}</span>
              </div>
            </button>
          </div>
        </section>
      </section>
    </main>

    <main v-else class="shell">
      <aside class="shell-sidebar">
        <div class="shell-brand">
          <div class="shell-brand__mark">AI</div>
          <div>
            <div class="shell-brand__title">AI 代码生成</div>
            <div class="shell-brand__caption">专业工作台</div>
          </div>
        </div>

        <button class="shell-create" type="button" @click="startNewGeneration">新建生成</button>

        <nav class="shell-nav">
          <button
            v-for="item in navItems"
            :key="item.path"
            type="button"
            :class="['shell-nav__item', { 'is-active': state.route === item.path }]"
            @click="navigate(item.path)"
          >
            <span class="shell-nav__label">{{ item.label }}</span>
            <span class="shell-nav__caption">{{ item.caption }}</span>
          </button>
        </nav>

        <div class="shell-sidebar__footer">
          <button class="shell-settings-link" type="button" @click="navigate('/settings')">设置</button>
          <div class="shell-user">
            <div class="shell-user__avatar">{{ state.user?.userName?.slice(0, 1) || 'A' }}</div>
            <div>
              <div class="shell-user__name">{{ state.user?.userName || state.user?.userAccount || '管理员' }}</div>
              <div class="shell-user__meta">{{ state.user?.userRole || 'user' }}</div>
            </div>
          </div>
          <button class="shell-logout" type="button" :disabled="state.loading" @click="logout">
            {{ state.loading ? '退出中...' : '退出登录' }}
          </button>
        </div>
      </aside>

      <section class="shell-main">
        <header class="shell-header">
          <div>
            <div class="shell-header__eyebrow">{{ activeRoute?.label }}</div>
            <h1 class="shell-header__title">{{ activeRoute?.label }}</h1>
            <p class="shell-header__subtitle">{{ activeRoute?.caption }}</p>
          </div>
          <div class="shell-header__actions">
            <span class="shell-chip">账号体系已接入</span>
            <span class="shell-chip shell-chip--muted">{{ state.user?.userAccount }}</span>
          </div>
        </header>

        <div v-if="state.message" :class="['shell-banner', 'shell-banner--' + state.messageType]">
          {{ state.message }}
        </div>

        <section v-if="state.route === '/'" class="page-grid">
          <article class="console-hero">
            <div class="console-hero__header">
              <div>
                <span class="panel-tag">生成控制台</span>
                <h2>把一个想法转成可运行代码</h2>
                <p>先写下你的需求，再选择适合的工作模式，我们后续把真实生成链路直接接进这里。</p>
              </div>
              <div class="console-mode">
                <span>当前模式</span>
                <strong>{{ state.selectedMode }}</strong>
              </div>
            </div>

            <div class="console-modes">
              <button
                v-for="mode in MODE_OPTIONS"
                :key="mode"
                type="button"
                :class="['mode-pill', { 'is-active': state.selectedMode === mode }]"
                @click="state.selectedMode = mode"
              >
                {{ mode }}
              </button>
            </div>

            <label class="console-input">
              <span>需求描述</span>
              <textarea
                v-model="state.generationInput"
                placeholder="例如：帮我生成一个带登录、项目列表、权限控制的企业管理后台。"
              ></textarea>
            </label>

            <div class="console-actions">
              <button class="primary-action" type="button" @click="submitGeneration">开始生成</button>
              <button class="ghost-action" type="button" @click="state.generationInput = ''">清空输入</button>
            </div>
          </article>

          <article class="panel-card panel-card--recent">
            <div class="panel-head">
              <div>
                <span class="panel-tag">继续工作</span>
                <h3>最近项目</h3>
              </div>
              <button class="text-action" type="button" @click="navigate('/projects')">查看全部</button>
            </div>
            <div class="item-stack">
              <div v-for="project in PROJECT_ITEMS" :key="project.name" class="project-row">
                <div>
                  <strong>{{ project.name }}</strong>
                  <span>{{ project.tag }}</span>
                </div>
                <small>{{ project.status }}</small>
              </div>
            </div>
          </article>

          <article class="panel-card">
            <div class="panel-head">
              <div>
                <span class="panel-tag">快速开始</span>
                <h3>模板 / 灵感</h3>
              </div>
              <button class="text-action" type="button" @click="navigate('/templates')">进入模板库</button>
            </div>
            <div class="prompt-grid">
              <button
                v-for="prompt in QUICK_PROMPTS"
                :key="prompt.title"
                class="prompt-card"
                type="button"
                @click="pickPrompt(prompt.detail)"
              >
                <strong>{{ prompt.title }}</strong>
                <span>{{ prompt.detail }}</span>
              </button>
            </div>
          </article>

          <article class="panel-card">
            <div class="panel-head">
              <div>
                <span class="panel-tag">系统反馈</span>
                <h3>当前产品状态</h3>
              </div>
            </div>
            <ul class="status-list">
              <li>登录 / 注册链路已接入后端接口</li>
              <li>旧前端页面已清空，新的产品骨架已接管</li>
              <li>下一步可以继续接入真实项目、历史和模板接口</li>
            </ul>
          </article>
        </section>

        <section v-else-if="state.route === '/projects'" class="page-grid page-grid--single">
          <article class="panel-card panel-card--full">
            <div class="panel-head">
              <div>
                <span class="panel-tag">项目中心</span>
                <h2>我的项目</h2>
              </div>
              <button class="ghost-action" type="button" @click="startNewGeneration">新建项目</button>
            </div>
            <div class="project-board">
              <div v-for="project in PROJECT_ITEMS" :key="project.name" class="project-board__card">
                <strong>{{ project.name }}</strong>
                <span>{{ project.tag }}</span>
                <small>{{ project.status }}</small>
              </div>
            </div>
          </article>
        </section>

        <section v-else-if="state.route === '/history'" class="page-grid page-grid--single">
          <article class="panel-card panel-card--full">
            <div class="panel-head">
              <div>
                <span class="panel-tag">会话轨迹</span>
                <h2>历史记录</h2>
              </div>
            </div>
            <div class="history-list">
              <div v-for="item in HISTORY_ITEMS" :key="item.title" class="history-item">
                <div>
                  <strong>{{ item.title }}</strong>
                  <span>{{ item.type }}</span>
                </div>
                <small>{{ item.time }}</small>
              </div>
            </div>
          </article>
        </section>

        <section v-else-if="state.route === '/templates'" class="page-grid page-grid--single">
          <article class="panel-card panel-card--full">
            <div class="panel-head">
              <div>
                <span class="panel-tag">模版资源</span>
                <h2>模板 / 灵感</h2>
              </div>
            </div>
            <div class="template-columns">
              <div v-for="group in TEMPLATE_GROUPS" :key="group.name" class="template-column">
                <h3>{{ group.name }}</h3>
                <button
                  v-for="item in group.items"
                  :key="item"
                  class="template-chip"
                  type="button"
                  @click="pickPrompt('请基于「' + item + '」这个方向帮我开始构建产品。')"
                >
                  {{ item }}
                </button>
              </div>
            </div>
          </article>
        </section>

        <section v-else-if="state.route === '/settings'" class="page-grid page-grid--single">
          <article class="panel-card panel-card--full">
            <div class="panel-head">
              <div>
                <span class="panel-tag">账户与偏好</span>
                <h2>设置</h2>
              </div>
            </div>
            <div class="settings-grid">
              <div class="settings-box">
                <span>当前账号</span>
                <strong>{{ state.user?.userAccount }}</strong>
              </div>
              <div class="settings-box">
                <span>显示名称</span>
                <strong>{{ state.user?.userName }}</strong>
              </div>
              <div class="settings-box">
                <span>角色</span>
                <strong>{{ state.user?.userRole }}</strong>
              </div>
              <div class="settings-box">
                <span>当前状态</span>
                <strong>骨架阶段已就绪</strong>
              </div>
            </div>
          </article>
        </section>
      </section>
    </main>
  `
}).mount("#app");
