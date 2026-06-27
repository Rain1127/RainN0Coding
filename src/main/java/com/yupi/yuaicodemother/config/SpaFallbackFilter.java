package com.yupi.yuaicodemother.config;

import jakarta.servlet.*;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.util.Set;

/**
 * SPA fallback: serve index.html for Vue Router routes so client-side routing works on page refresh.
 */
@Component
@Order(Integer.MIN_VALUE)
public class SpaFallbackFilter implements Filter {

    private static final Set<String> SPA_ROUTES = Set.of(
            "/api/login",
            "/api/register",
            "/api/403"
    );

    private static final Set<String> SPA_PREFIXES = Set.of(
            "/api/chat/",
            "/api/admin/"
    );

    @Override
    public void doFilter(ServletRequest req, ServletResponse res, FilterChain chain)
            throws IOException, ServletException {
        HttpServletRequest request = (HttpServletRequest) req;

        if ("GET".equalsIgnoreCase(request.getMethod()) && isSpaRoute(request.getRequestURI())) {
            request.getRequestDispatcher("/").forward(request, res);
            return;
        }

        chain.doFilter(request, res);
    }

    private boolean isSpaRoute(String path) {
        if (SPA_ROUTES.contains(path)) {
            return true;
        }
        for (String prefix : SPA_PREFIXES) {
            if (path.startsWith(prefix)) {
                return true;
            }
        }
        return false;
    }
}
