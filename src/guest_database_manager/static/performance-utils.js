/**
 * Performance and UX Utilities for Mirror Talk Dashboard
 * Provides debouncing, caching, loading states, and request deduplication
 */

// ==================== Debouncing ====================

/**
 * Creates a debounced function that delays execution until after delay ms have elapsed
 * since the last time it was invoked.
 */
function debounce(func, delay = 300) {
  let timeoutId = null;
  let lastArgs = null;
  
  const debounced = function(...args) {
    lastArgs = args;
    clearTimeout(timeoutId);
    timeoutId = setTimeout(() => {
      func.apply(this, lastArgs);
      timeoutId = null;
      lastArgs = null;
    }, delay);
  };
  
  debounced.cancel = function() {
    clearTimeout(timeoutId);
    timeoutId = null;
    lastArgs = null;
  };
  
  debounced.flush = function() {
    if (timeoutId !== null && lastArgs !== null) {
      clearTimeout(timeoutId);
      func.apply(this, lastArgs);
      timeoutId = null;
      lastArgs = null;
    }
  };
  
  return debounced;
}

/**
 * Creates a throttled function that only executes at most once per interval.
 */
function throttle(func, interval = 300) {
  let lastCallTime = 0;
  let timeoutId = null;
  
  return function(...args) {
    const now = Date.now();
    const timeSinceLastCall = now - lastCallTime;
    
    if (timeSinceLastCall >= interval) {
      lastCallTime = now;
      func.apply(this, args);
    } else {
      clearTimeout(timeoutId);
      timeoutId = setTimeout(() => {
        lastCallTime = Date.now();
        func.apply(this, args);
      }, interval - timeSinceLastCall);
    }
  };
}

// ==================== Request Deduplication ====================

/**
 * Prevents duplicate in-flight requests for the same resource.
 * If a request is already in progress, returns the existing promise.
 */
class RequestDeduplicator {
  constructor() {
    this.inFlightRequests = new Map();
  }
  
  async dedupe(key, requestFn) {
    // If request already in flight, return existing promise
    if (this.inFlightRequests.has(key)) {
      return this.inFlightRequests.get(key);
    }
    
    // Start new request
    const promise = requestFn()
      .finally(() => {
        // Clean up when request completes
        this.inFlightRequests.delete(key);
      });
    
    this.inFlightRequests.set(key, promise);
    return promise;
  }
  
  clear(key) {
    if (key) {
      this.inFlightRequests.delete(key);
    } else {
      this.inFlightRequests.clear();
    }
  }
  
  isInFlight(key) {
    return this.inFlightRequests.has(key);
  }
}

// ==================== Loading State Management ====================

/**
 * Manages loading states for UI elements with automatic cleanup.
 */
class LoadingStateManager {
  constructor() {
    this.activeStates = new Map();
  }
  
  /**
   * Start loading state for a button or element
   */
  start(element, options = {}) {
    if (!element) return;
    
    const id = options.id || this._generateId(element);
    const originalText = element.textContent || element.innerText;
    const originalDisabled = element.disabled;
    const loadingText = options.loadingText || "Loading...";
    
    this.activeStates.set(id, {
      element,
      originalText,
      originalDisabled,
      startTime: Date.now()
    });
    
    element.disabled = true;
    element.classList.add('loading');
    if (element.tagName === 'BUTTON' || element.tagName === 'INPUT') {
      element.textContent = loadingText;
    }
    
    return id;
  }
  
  /**
   * End loading state for an element
   */
  end(idOrElement, options = {}) {
    const id = typeof idOrElement === 'string' ? idOrElement : this._generateId(idOrElement);
    const state = this.activeStates.get(id);
    
    if (!state) return;
    
    const { element, originalText, originalDisabled } = state;
    
    element.disabled = options.keepDisabled ? true : originalDisabled;
    element.classList.remove('loading');
    
    if (options.successText) {
      element.textContent = options.successText;
      setTimeout(() => {
        if (this.activeStates.has(id)) {
          element.textContent = originalText;
        }
      }, 2000);
    } else if (options.errorText) {
      element.textContent = options.errorText;
      setTimeout(() => {
        if (this.activeStates.has(id)) {
          element.textContent = originalText;
        }
      }, 3000);
    } else {
      element.textContent = originalText;
    }
    
    this.activeStates.delete(id);
  }
  
  /**
   * Execute an async function with automatic loading state management
   */
  async wrap(element, asyncFn, options = {}) {
    const id = this.start(element, options);
    try {
      const result = await asyncFn();
      this.end(id, { successText: options.successText });
      return result;
    } catch (error) {
      this.end(id, { errorText: options.errorText || 'Error' });
      throw error;
    }
  }
  
  _generateId(element) {
    if (!element._loadingId) {
      element._loadingId = `loading_${Math.random().toString(36).substr(2, 9)}`;
    }
    return element._loadingId;
  }
}

// ==================== Smart Cache ====================

/**
 * Smart caching with TTL and size limits
 */
class SmartCache {
  constructor(options = {}) {
    this.cache = new Map();
    this.maxSize = options.maxSize || 50;
    this.defaultTTL = options.defaultTTL || 5 * 60 * 1000; // 5 minutes
  }
  
  set(key, value, ttl = this.defaultTTL) {
    // Evict oldest if at capacity
    if (this.cache.size >= this.maxSize) {
      const firstKey = this.cache.keys().next().value;
      this.cache.delete(firstKey);
    }
    
    this.cache.set(key, {
      value,
      expires: ttl ? Date.now() + ttl : null
    });
  }
  
  get(key) {
    const entry = this.cache.get(key);
    if (!entry) return null;
    
    // Check expiration
    if (entry.expires && Date.now() > entry.expires) {
      this.cache.delete(key);
      return null;
    }
    
    return entry.value;
  }
  
  has(key) {
    return this.get(key) !== null;
  }
  
  delete(key) {
    this.cache.delete(key);
  }
  
  clear() {
    this.cache.clear();
  }
  
  prune() {
    const now = Date.now();
    for (const [key, entry] of this.cache.entries()) {
      if (entry.expires && now > entry.expires) {
        this.cache.delete(key);
      }
    }
  }
}

// ==================== Keyboard Shortcuts ====================

/**
 * Keyboard shortcut manager with command palette support
 */
class KeyboardShortcutManager {
  constructor() {
    this.shortcuts = new Map();
    this.enabled = true;
    this._boundHandler = this._handleKeyDown.bind(this);
  }
  
  register(shortcut, handler, description = '') {
    const normalizedShortcut = this._normalizeShortcut(shortcut);
    this.shortcuts.set(normalizedShortcut, { handler, description });
  }
  
  unregister(shortcut) {
    const normalizedShortcut = this._normalizeShortcut(shortcut);
    this.shortcuts.delete(normalizedShortcut);
  }
  
  enable() {
    if (!this.enabled) {
      this.enabled = true;
      document.addEventListener('keydown', this._boundHandler);
    }
  }
  
  disable() {
    if (this.enabled) {
      this.enabled = false;
      document.removeEventListener('keydown', this._boundHandler);
    }
  }
  
  _normalizeShortcut(shortcut) {
    return shortcut.toLowerCase()
      .replace(/\s+/g, '')
      .replace('cmd', 'meta')
      .split('+')
      .sort()
      .join('+');
  }
  
  _handleKeyDown(event) {
    // Don't trigger shortcuts when user is typing in inputs
    const target = event.target;
    if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) {
      // Allow Escape to work even in inputs
      if (event.key !== 'Escape') {
        return;
      }
    }
    
    const keys = [];
    if (event.ctrlKey) keys.push('ctrl');
    if (event.altKey) keys.push('alt');
    if (event.shiftKey) keys.push('shift');
    if (event.metaKey) keys.push('meta');
    
    const key = event.key.toLowerCase();
    if (!['control', 'alt', 'shift', 'meta'].includes(key)) {
      keys.push(key);
    }
    
    const shortcut = keys.sort().join('+');
    const handler = this.shortcuts.get(shortcut);
    
    if (handler) {
      event.preventDefault();
      handler.handler(event);
    }
  }
  
  getShortcuts() {
    return Array.from(this.shortcuts.entries()).map(([shortcut, { description }]) => ({
      shortcut: shortcut.replace('meta', navigator.platform.includes('Mac') ? '⌘' : 'Ctrl'),
      description
    }));
  }
}

// ==================== Optimistic UI Updates ====================

/**
 * Manages optimistic UI updates with rollback on error
 */
class OptimisticUpdateManager {
  constructor() {
    this.pendingUpdates = new Map();
  }
  
  async apply(id, optimisticFn, actualFn, rollbackFn) {
    // Apply optimistic update immediately
    const rollbackState = optimisticFn();
    
    this.pendingUpdates.set(id, { rollbackState, rollbackFn });
    
    try {
      // Perform actual operation
      const result = await actualFn();
      this.pendingUpdates.delete(id);
      return result;
    } catch (error) {
      // Rollback on error
      if (this.pendingUpdates.has(id)) {
        const { rollbackState, rollbackFn } = this.pendingUpdates.get(id);
        rollbackFn(rollbackState);
        this.pendingUpdates.delete(id);
      }
      throw error;
    }
  }
  
  rollback(id) {
    if (this.pendingUpdates.has(id)) {
      const { rollbackState, rollbackFn } = this.pendingUpdates.get(id);
      rollbackFn(rollbackState);
      this.pendingUpdates.delete(id);
    }
  }
  
  clear() {
    this.pendingUpdates.clear();
  }
}

// ==================== Error Recovery ====================

/**
 * Retry failed requests with exponential backoff
 */
async function retryWithBackoff(fn, options = {}) {
  const maxRetries = options.maxRetries || 3;
  const baseDelay = options.baseDelay || 1000;
  const maxDelay = options.maxDelay || 10000;
  const shouldRetry = options.shouldRetry || (() => true);
  
  let lastError;
  
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;
      
      if (attempt === maxRetries || !shouldRetry(error, attempt)) {
        throw error;
      }
      
      // Calculate delay with exponential backoff and jitter
      const delay = Math.min(
        baseDelay * Math.pow(2, attempt) + Math.random() * 1000,
        maxDelay
      );
      
      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }
  
  throw lastError;
}

/**
 * Show user-friendly error messages
 */
function getUserFriendlyError(error) {
  if (!error) return 'An unknown error occurred';
  
  const message = error.message || String(error);
  
  // Network errors
  if (message.includes('fetch') || message.includes('network') || message.includes('NetworkError')) {
    return 'Connection issue. Please check your internet and try again.';
  }
  
  // Server errors
  if (message.includes('500') || message.includes('Internal Server Error')) {
    return 'Server error. Please try again in a moment.';
  }
  
  // Timeout errors
  if (message.includes('timeout') || message.includes('timed out')) {
    return 'Request timed out. Please try again.';
  }
  
  // Permission errors
  if (message.includes('403') || message.includes('Forbidden') || message.includes('unauthorized')) {
    return 'Permission denied. Please log in again.';
  }
  
  // Not found errors
  if (message.includes('404') || message.includes('Not Found')) {
    return 'Resource not found. It may have been deleted.';
  }
  
  return message;
}

// ==================== Export ====================

window.PerformanceUtils = {
  debounce,
  throttle,
  RequestDeduplicator,
  LoadingStateManager,
  SmartCache,
  KeyboardShortcutManager,
  OptimisticUpdateManager,
  retryWithBackoff,
  getUserFriendlyError
};
