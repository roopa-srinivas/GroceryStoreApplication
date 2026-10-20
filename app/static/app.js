// Fresh Market pages. Everything goes through the JSON API in app/api.py.
// Names come from the database, so they're always set with textContent.

const $ = (sel) => document.querySelector(sel);
const money = (cents) => `$${(cents / 100).toFixed(2)}`;

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === 'class') node.className = v;
    else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) node.setAttribute(k, v === true ? '' : v);
  }
  node.append(...children.filter((c) => c != null && c !== false));
  return node;
}

async function api(path, options = {}) {
  const res = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error(data.error || 'Something went wrong.'), { data, status: res.status });
  return data;
}

let toastTimer;
function toast(message, bad = false) {
  const t = $('#toast');
  t.textContent = message;
  t.classList.toggle('bad', bad);
  t.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('show'), 3500);
}

const STATUS_LABEL = { ok: 'In stock', low: 'Low stock', out: 'Out of stock' };
const pill = (status, text) => el('span', { class: `pill ${status}` }, text);

function chips(container, options, current, onPick) {
  container.replaceChildren(...options.map(([value, label]) =>
    el('button', { type: 'button', class: `chip${value === current ? ' on' : ''}`, 'aria-pressed': String(value === current), onclick: () => onPick(value) }, label)));
}

const debounce = (fn, ms = 200) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

// ----- shop -----------------------------------------------------------------------
async function storePage() {
  const state = { category: null, cart: new Map(), products: [] };
  const categories = await api('/categories');

  function renderChips() {
    chips($('#categories'), [[null, 'All'], ...categories.map((c) => [c.id, c.name])], state.category, (v) => { state.category = v; renderChips(); load(); });
  }

  async function load() {
    const params = new URLSearchParams({ sort: $('#sort').value });
    if ($('#search').value.trim()) params.set('q', $('#search').value.trim());
    if (state.category) params.set('category', state.category);
    if ($('#in-stock').checked) params.set('in_stock', '1');
    state.products = await api(`/products?${params}`);
    const grid = $('#products');
    if (!state.products.length) return grid.replaceChildren(el('p', { class: 'muted' }, 'No products match.'));
    grid.replaceChildren(...state.products.map((p) => {
      const inCart = state.cart.get(p.id)?.qty || 0;
      const soldOut = p.stock_qty === 0 || inCart >= p.stock_qty;
      return el('article', { class: 'product' },
        el('div', { class: 'emoji', 'aria-hidden': 'true' }, p.emoji),
        el('h3', {}, p.name),
        el('p', { class: 'muted small' }, p.category),
        p.status !== 'ok' ? pill(p.status, p.status === 'low' ? `Only ${p.stock_qty} left` : 'Out of stock') : null,
        el('div', { class: 'product-foot' },
          el('b', {}, money(p.price_cents)),
          el('button', { type: 'button', class: 'btn small', disabled: soldOut, onclick: () => add(p) }, soldOut && p.stock_qty ? 'All in cart' : '+ Add')));
    }));
  }

  function add(p) {
    const line = state.cart.get(p.id) || { product: p, qty: 0 };
    line.qty += 1;
    line.product = p;
    state.cart.set(p.id, line);
    renderCart();
    load();
  }

  function renderCart() {
    const lines = [...state.cart.values()];
    $('#cart-items').replaceChildren(...(lines.length ? lines.map(({ product, qty }) =>
      el('div', { class: 'cart-line' },
        el('span', {}, `${product.emoji} ${product.name}`),
        el('span', { class: 'qty' },
          el('button', { type: 'button', 'aria-label': `One fewer ${product.name}`, onclick: () => change(product.id, -1) }, '−'),
          el('b', {}, String(qty)),
          el('button', { type: 'button', 'aria-label': `One more ${product.name}`, disabled: qty >= product.stock_qty, onclick: () => change(product.id, 1) }, '+')),
        el('span', { class: 'num' }, money(product.price_cents * qty)))) : [el('p', { class: 'muted small' }, 'Nothing here yet.')]));
    $('#cart-total').textContent = money(lines.reduce((sum, l) => sum + l.product.price_cents * l.qty, 0));
    $('#checkout button').disabled = !lines.length;
  }

  function change(id, delta) {
    const line = state.cart.get(id);
    line.qty += delta;
    if (line.qty <= 0) state.cart.delete(id);
    renderCart();
    load();
  }

  $('#checkout').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = new FormData(event.target);
    try {
      const order = await api('/orders', {
        method: 'POST',
        body: { customer: { name: form.get('name'), email: form.get('email') }, items: [...state.cart.values()].map((l) => ({ product_id: l.product.id, qty: l.qty })) },
      });
      state.cart.clear();
      toast(`Order #${order.id} placed: ${money(order.total_cents)}. Thank you!`);
    } catch (err) {
      // Someone else bought the last ones first: say which, keep the cart.
      const short = err.data?.short?.map((id) => state.cart.get(id)?.product.name).filter(Boolean);
      toast(short?.length ? `Not enough stock for: ${short.join(', ')}. Your cart is unchanged.` : err.message, true);
    }
    renderCart();
    load();
  });

  $('#search').addEventListener('input', debounce(load));
  $('#sort').addEventListener('change', load);
  $('#in-stock').addEventListener('change', load);
  renderChips();
  renderCart();
  load();
}

// ----- orders ------------------------------------------------------------------------
const ACTIONS = { processing: [['shipped', 'Mark shipped'], ['cancelled', 'Cancel']], shipped: [['delivered', 'Mark delivered']] };

async function ordersPage() {
  let filter = '';
  const statuses = [['', 'All'], ['processing', 'Processing'], ['shipped', 'Shipped'], ['delivered', 'Delivered'], ['cancelled', 'Cancelled']];
  async function load() {
    chips($('#status-filter'), statuses, filter, (v) => { filter = v; load(); });
    const orders = await api(`/orders${filter ? `?status=${filter}` : ''}`);
    $('#orders').replaceChildren(...(orders.length ? orders.map((o) => el('tr', {},
      el('td', {}, `#${o.id}`),
      el('td', {}, o.customer.name),
      el('td', { class: 'small' }, o.items.map((i) => `${i.name} × ${i.qty}`).join(', ')),
      el('td', { class: 'num' }, money(o.total_cents)),
      el('td', { class: 'small' }, new Date(o.created_at).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })),
      el('td', {}, pill(o.status, o.status[0].toUpperCase() + o.status.slice(1))),
      el('td', {}, el('div', { class: 'actions' }, ...(ACTIONS[o.status] || []).map(([status, label]) =>
        el('button', { type: 'button', class: `btn small${status === 'cancelled' ? ' ghost' : ''}`, onclick: () => move(o.id, status) }, label))))))
      : [el('tr', {}, el('td', { colspan: '7', class: 'muted' }, 'No orders here.'))]));
  }
  async function move(id, status) {
    try {
      await api(`/orders/${id}`, { method: 'PATCH', body: { status } });
      toast(status === 'cancelled' ? `Order #${id} cancelled and its items restocked.` : `Order #${id} is ${status}.`);
    } catch (err) {
      toast(err.message, true);
    }
    load();
  }
  load();
}

// ----- inventory ---------------------------------------------------------------------
async function inventoryPage() {
  const categories = await api('/categories');
  $('#add-category').replaceChildren(el('option', { value: '' }, 'Category'), ...categories.map((c) => el('option', { value: c.id }, c.name)));

  async function load() {
    const all = await api('/products?sort=stock');
    const counts = { total: all.length, low: all.filter((p) => p.status === 'low').length, out: all.filter((p) => p.status === 'out').length };
    const value = all.reduce((sum, p) => sum + p.price_cents * p.stock_qty, 0);
    $('#stats').replaceChildren(
      el('div', { class: 'stat' }, el('b', {}, String(counts.total)), el('span', {}, 'products')),
      el('div', { class: 'stat' }, el('b', {}, String(counts.low)), el('span', {}, 'low on stock')),
      el('div', { class: 'stat' }, el('b', {}, String(counts.out)), el('span', {}, 'out of stock')),
      el('div', { class: 'stat' }, el('b', {}, money(value)), el('span', {}, 'stock value at retail')));
    const q = $('#search').value.trim().toLowerCase();
    const rows = all.filter((p) => (!q || p.name.toLowerCase().includes(q) || p.sku.toLowerCase().includes(q)) && (!$('#low-only').checked || p.status !== 'ok'));
    $('#inventory').replaceChildren(...rows.map((p) => {
      const input = el('input', { type: 'number', min: '1', max: '10000', value: '12', 'aria-label': `Units of ${p.name} to add` });
      return el('tr', {},
        el('td', { class: 'small mono' }, p.sku),
        el('td', {}, `${p.emoji} ${p.name}`),
        el('td', { class: 'small' }, p.category),
        el('td', { class: 'num' }, money(p.price_cents)),
        el('td', { class: 'num' }, String(p.stock_qty)),
        el('td', {}, pill(p.status, STATUS_LABEL[p.status])),
        el('td', { class: 'restock' }, input, el('button', { type: 'button', class: 'btn small', onclick: () => restock(p, input.value) }, 'Add')));
    }));
  }
  async function restock(p, qty) {
    try {
      const updated = await api(`/products/${p.id}/restock`, { method: 'POST', body: { qty: Number(qty) } });
      toast(`${p.name}: ${updated.stock_qty} in stock.`);
    } catch (err) {
      toast(err.message, true);
    }
    load();
  }
  $('#add-product').addEventListener('submit', async (event) => {
    event.preventDefault();
    const f = new FormData(event.target);
    try {
      const p = await api('/products', {
        method: 'POST',
        body: { sku: f.get('sku'), name: f.get('name'), category_id: Number(f.get('category_id')), price_cents: Math.round(Number(f.get('price')) * 100), stock_qty: Number(f.get('stock_qty')), emoji: f.get('emoji') },
      });
      event.target.reset();
      toast(`Added ${p.name}.`);
      load();
    } catch (err) {
      toast(err.message, true);
    }
  });
  $('#search').addEventListener('input', debounce(load));
  $('#low-only').addEventListener('change', load);
  load();
}

// ----- reports -----------------------------------------------------------------------
function bars(container, rows, label, valueOf, format) {
  const max = Math.max(...rows.map(valueOf), 1);
  container.replaceChildren(...(rows.length ? rows.map((r) => el('div', { class: 'bar-row' },
    el('div', { class: 'bar-label' }, el('span', {}, label(r)), el('b', {}, format(r))),
    el('div', { class: 'bar' }, Object.assign(el('span'), { style: `width:${(valueOf(r) / max) * 100}%` }))))
    : [el('p', { class: 'muted small' }, 'No sales in this period.')]));
}

async function reportsPage() {
  async function load() {
    const r = await api(`/reports?days=${$('#days').value}`);
    bars($('#revenue'), r.revenue_by_category, (x) => x.category, (x) => x.revenue_cents, (x) => `${money(x.revenue_cents)} · ${x.units} units`);
    bars($('#top'), r.top_products, (x) => `${x.emoji} ${x.name}`, (x) => x.units, (x) => `${x.units} sold`);
    $('#low').replaceChildren(...(r.low_stock.length ? r.low_stock.map((p) => el('div', { class: 'low-row' },
      el('span', {}, `${p.emoji} ${p.name}`), pill(p.stock_qty === 0 ? 'out' : 'low', p.stock_qty === 0 ? 'Out' : `${p.stock_qty} left`)))
      : [el('p', { class: 'muted small' }, 'Everything is well stocked.')]));
    const order = ['processing', 'shipped', 'delivered', 'cancelled'];
    $('#statuses').replaceChildren(...order.map((s) => el('div', { class: 'low-row' }, pill(s, s[0].toUpperCase() + s.slice(1)), el('b', {}, String(r.orders_by_status[s] || 0)))));
    $('#sql-revenue').textContent = r.sql.revenue_by_category;
    $('#sql-top').textContent = r.sql.top_products;
    $('#sql-low').textContent = r.sql.low_stock;
    $('#sql-status').textContent = r.sql.orders_by_status;
  }
  $('#days').addEventListener('change', load);
  load();
}

const PAGES = { store: storePage, orders: ordersPage, inventory: inventoryPage, reports: reportsPage };
PAGES[document.body.dataset.page]?.().catch((err) => toast(err.message, true));
