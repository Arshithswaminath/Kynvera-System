/**
 * Production-safe logging utility
 * Removes console.log statements in production builds
 */
(function() {
    'use strict';
    
    // Check if we're in production (you can set this via a global variable or meta tag)
    const isProduction = typeof window !== 'undefined' && (
        window.location.hostname !== 'localhost' && 
        window.location.hostname !== '127.0.0.1' &&
        !window.location.hostname.startsWith('192.168.') &&
        !window.location.hostname.startsWith('10.') &&
        !window.location.hostname.includes('.local')
    );
    
    // Create a safe logger that only logs in development
    window.safeLog = {
        log: function(...args) {
            if (!isProduction) {
                console.log(...args);
            }
        },
        error: function(...args) {
            // Always log errors, even in production
            console.error(...args);
        },
        warn: function(...args) {
            if (!isProduction) {
                console.warn(...args);
            }
        },
        info: function(...args) {
            if (!isProduction) {
                console.info(...args);
            }
        },
        debug: function(...args) {
            if (!isProduction) {
                console.debug(...args);
            }
        }
    };
    
    // Optionally override console.log in production (more aggressive)
    if (isProduction && typeof window !== 'undefined') {
        // Keep console.error and console.warn for actual errors
        // But remove console.log, console.info, console.debug
        const originalLog = console.log;
        const originalInfo = console.info;
        const originalDebug = console.debug;
        
        console.log = function() {
            // Silently ignore in production
        };
        console.info = function() {
            // Silently ignore in production
        };
        console.debug = function() {
            // Silently ignore in production
        };
        
        // Restore on window focus for debugging (developer escape hatch)
        window.addEventListener('focus', function() {
            // Don't restore - keep it disabled
        });
    }
})();

