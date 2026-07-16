package com.rain.rainn0coding.config;

import jakarta.servlet.FilterChain;
import jakarta.servlet.RequestDispatcher;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServletRequest;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class SpaFallbackFilterTest {

    @ParameterizedTest
    @ValueSource(strings = {
            "/api/",
            "/api/login",
            "/api/register",
            "/api/projects",
            "/api/chat/42",
            "/api/admin/apps",
            "/api/admin/apps/42",
            "/api/admin/users",
            "/api/admin/intent-tree",
            "/api/403",
            "/api/a-missing-page"
    })
    void shouldForwardSpaNavigationInsideContextPath(String requestUri) throws Exception {
        SpaFallbackFilter filter = new SpaFallbackFilter();
        HttpServletRequest request = htmlGet(requestUri, "/api");
        ServletResponse response = mock(ServletResponse.class);
        FilterChain chain = mock(FilterChain.class);
        RequestDispatcher dispatcher = mock(RequestDispatcher.class);
        when(request.getRequestDispatcher("/index.html")).thenReturn(dispatcher);

        filter.doFilter(request, response, chain);

        verify(dispatcher).forward(request, response);
        verify(chain, never()).doFilter(request, response);
    }

    @ParameterizedTest
    @ValueSource(strings = {
            "/login",
            "/chat/7",
            "/admin/apps/7",
            "/missing-page"
    })
    void shouldAlsoRecognizeSpaNavigationWithoutAContextPath(String requestUri) throws Exception {
        SpaFallbackFilter filter = new SpaFallbackFilter();
        HttpServletRequest request = htmlGet(requestUri, "");
        ServletResponse response = mock(ServletResponse.class);
        FilterChain chain = mock(FilterChain.class);
        RequestDispatcher dispatcher = mock(RequestDispatcher.class);
        when(request.getRequestDispatcher("/index.html")).thenReturn(dispatcher);

        filter.doFilter(request, response, chain);

        verify(dispatcher).forward(request, response);
        verify(chain, never()).doFilter(request, response);
    }

    @ParameterizedTest
    @ValueSource(strings = {
            "/api/app/get/vo",
            "/api/app/chat/gen/code",
            "/api/user/get/login",
            "/api/chatHistory/app/42",
            "/api/intent-config/tree",
            "/api/health/",
            "/api/actuator/health",
            "/api/static/deploy-key/index.html",
            "/api/assets/index-abc123.js",
            "/api/favicon.svg",
            "/api/readme.txt"
    })
    void shouldNotForwardBusinessStaticOrExtensionRequests(String requestUri) throws Exception {
        SpaFallbackFilter filter = new SpaFallbackFilter();
        HttpServletRequest request = htmlGet(requestUri, "/api");
        ServletResponse response = mock(ServletResponse.class);
        FilterChain chain = mock(FilterChain.class);

        filter.doFilter(request, response, chain);

        verify(chain).doFilter(request, response);
        verify(request, never()).getRequestDispatcher("/index.html");
    }

    @ParameterizedTest
    @ValueSource(strings = {"POST", "PUT", "DELETE"})
    void shouldNotForwardMutatingRequests(String method) throws Exception {
        SpaFallbackFilter filter = new SpaFallbackFilter();
        HttpServletRequest request = mock(HttpServletRequest.class);
        ServletResponse response = mock(ServletResponse.class);
        FilterChain chain = mock(FilterChain.class);
        when(request.getMethod()).thenReturn(method);
        when(request.getRequestURI()).thenReturn("/api/projects");
        when(request.getContextPath()).thenReturn("/api");
        when(request.getHeader("Accept")).thenReturn("text/html");

        filter.doFilter(request, response, chain);

        verify(chain).doFilter(request, response);
    }

    @ParameterizedTest
    @ValueSource(strings = {"application/json", "text/event-stream", "*/*"})
    void shouldNotTreatNonHtmlUnknownGetsAsSpaNavigation(String accept) throws Exception {
        SpaFallbackFilter filter = new SpaFallbackFilter();
        HttpServletRequest request = mock(HttpServletRequest.class);
        ServletResponse response = mock(ServletResponse.class);
        FilterChain chain = mock(FilterChain.class);
        when(request.getMethod()).thenReturn("GET");
        when(request.getRequestURI()).thenReturn("/api/future-endpoint");
        when(request.getContextPath()).thenReturn("/api");
        when(request.getHeader("Accept")).thenReturn(accept);

        filter.doFilter(request, response, chain);

        verify(chain).doFilter(request, response);
    }

    private HttpServletRequest htmlGet(String requestUri, String contextPath) {
        HttpServletRequest request = mock(HttpServletRequest.class);
        when(request.getMethod()).thenReturn("GET");
        when(request.getRequestURI()).thenReturn(requestUri);
        when(request.getContextPath()).thenReturn(contextPath);
        when(request.getHeader("Accept")).thenReturn("text/html,application/xhtml+xml");
        return request;
    }
}
