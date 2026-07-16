package com.rain.rainn0coding.config;

import jakarta.servlet.*;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.util.List;
import java.util.Locale;

/**
 * SPA fallback: serve index.html for Vue Router routes so client-side routing works on page refresh.
 */
@Component
@Order(Integer.MIN_VALUE)
public class SpaFallbackFilter implements Filter {

    private static final List<String> BACKEND_PREFIXES = List.of(
            "/app",
            "/appVersion",
            "/chatHistory",
            "/health",
            "/intent-config",
            "/static",
            "/user",
            "/actuator",
            "/v3",
            "/swagger-ui",
            "/webjars",
            "/error"
    );

    @Override
    public void doFilter(ServletRequest req, ServletResponse res, FilterChain chain)
            throws IOException, ServletException {
        HttpServletRequest request = (HttpServletRequest) req;

        if ("GET".equalsIgnoreCase(request.getMethod())
                && acceptsHtml(request)
                && isSpaRoute(pathWithinContext(request))) {
            request.getRequestDispatcher("/index.html").forward(request, res);
            return;
        }

        chain.doFilter(request, res);
    }

    private String pathWithinContext(HttpServletRequest request) {
        String path = request.getRequestURI();
        String contextPath = request.getContextPath();
        if (contextPath != null && !contextPath.isEmpty()
                && (path.equals(contextPath) || path.startsWith(contextPath + "/"))) {
            path = path.substring(contextPath.length());
        }
        return path.isEmpty() ? "/" : path;
    }

    private boolean acceptsHtml(HttpServletRequest request) {
        String accept = request.getHeader("Accept");
        return accept != null && accept.toLowerCase(Locale.ROOT).contains("text/html");
    }

    private boolean isSpaRoute(String path) {
        if (path == null || !path.startsWith("/")) return false;
        if (path.equals("/assets") || path.startsWith("/assets/")) return false;
        if (hasFileExtension(path)) return false;
        if (BACKEND_PREFIXES.stream().anyMatch(prefix -> path.equals(prefix) || path.startsWith(prefix + "/"))) {
            return false;
        }
        // Let Vue Router render its own 404 page for unknown browser navigations.
        return true;
    }

    private boolean hasFileExtension(String path) {
        int lastSlash = path.lastIndexOf('/');
        int lastDot = path.lastIndexOf('.');
        return lastDot > lastSlash;
    }
}
