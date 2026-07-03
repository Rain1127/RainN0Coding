package com.rain.rainn0coding.config;

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
            "/",
            "/api/",
            "/login",
            "/register",
            "/api/login",
            "/api/register",
            "/projects",
            "/history",
            "/templates",
            "/settings",
            "/api/projects",
            "/api/history",
            "/api/templates",
            "/api/settings"
    );

    @Override
    public void doFilter(ServletRequest req, ServletResponse res, FilterChain chain)
            throws IOException, ServletException {
        HttpServletRequest request = (HttpServletRequest) req;

        if ("GET".equalsIgnoreCase(request.getMethod()) && isSpaRoute(request.getRequestURI())) {
            request.getRequestDispatcher("/index.html").forward(request, res);
            return;
        }

        chain.doFilter(request, res);
    }

    private boolean isSpaRoute(String path) {
        return SPA_ROUTES.contains(path);
    }
}
