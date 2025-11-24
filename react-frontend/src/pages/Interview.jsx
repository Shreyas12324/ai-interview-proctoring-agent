import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { useInterview } from '../context/InterviewContext';
import { sendAnswer, endInterview } from '../services/api';
import Header from '../components/Header';
import ChatBubble from '../components/ChatBubble';
import ChatInput from '../components/ChatInput';
import WebcamFeed from '../components/WebcamFeed';

export default function Interview() {
  const navigate = useNavigate();
  const { interviewData, setInterviewData, addMessage } = useInterview();
  const messagesEndRef = useRef(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [alerts, setAlerts] = useState([]);

  // Redirect if no interview session
  useEffect(() => {
    if (!interviewData?.interviewId) {
      console.log('No interview ID found, redirecting to home');
      navigate('/');
    }
  }, [interviewData?.interviewId, navigate]);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [interviewData?.messages]);

  // Tab switching detection
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.hidden) {
        console.log('⚠️ User switched away from tab');
        toast.error('⚠ Tab switching detected!', {
          duration: 5000,
          style: {
            background: '#DC2626',
            color: '#fff',
            fontWeight: '600',
            fontSize: '14px',
          },
        });
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, []);

  const handleSendAnswer = async answer => {
    if (!interviewData?.interviewId) return;

    setLoading(true);
    setError('');

    try {
      // Add user message to UI
      const userMessage = {
        role: 'user',
        content: answer,
        timestamp: new Date().toISOString(),
      };
      addMessage(userMessage);

      // Send to backend
      const response = await sendAnswer({
        interview_id: interviewData.interviewId,
        user_answer: answer,
      });

      // Add agent response
      const agentResponse = {
        role: 'assistant',
        content: response.agent_response,
        timestamp: new Date().toISOString(),
      };
      addMessage(agentResponse);

      // Add next question if available
      if (response.next_question) {
        const nextQuestion = {
          role: 'assistant',
          content: response.next_question,
          timestamp: new Date().toISOString(),
          isFollowup: response.is_followup,
        };
        addMessage(nextQuestion);
      }

      // Check if interview ended
      if (response.interview_ended) {
        handleEndInterview();
      }
    } catch (err) {
      console.error('Error sending answer:', err);
      setError(
        err.response?.data?.detail || 'Failed to send answer. Please try again.'
      );
    } finally {
      setLoading(false);
    }
  };

  const handleEndInterview = async () => {
    if (!interviewData?.interviewId) return;

    setLoading(true);
    setError('');

    try {
      const response = await endInterview({
        interview_id: interviewData.interviewId,
      });

      // Store feedback in context
      setInterviewData({
        ...interviewData,
        feedback: response.feedback,
        cheating_summary: response.cheating_summary,
      });

      // Navigate to feedback page
      navigate('/feedback');
    } catch (err) {
      console.error('Error ending interview:', err);
      setError(
        err.response?.data?.detail ||
          'Failed to end interview. Please try again.'
      );
      setLoading(false);
    }
  };

  const handleCheatingAlert = alert => {
    if (!alert) {
      console.log('⚠️ Alert is null/undefined');
      return;
    }

    console.log('🔔 Cheating alert received:', alert);

    // Check if this is a critical alert that should show toast popup
    const eventType = alert.event_type || alert.eventType;
    const severity = alert.severity;

    console.log(`📊 Event Type: ${eventType}, Severity: ${severity}`);

    const isCritical =
      ['MOBILE_DEVICE_DETECTED'].includes(eventType) &&
      ['critical', 'high'].includes(severity);

    console.log(`🎯 Is Critical Alert: ${isCritical}`);

    // Only add critical alerts and show toast
    if (isCritical) {
      console.log('🚨 SHOWING TOAST NOTIFICATION');

      setAlerts(prev => [
        ...prev,
        {
          ...alert,
          timestamp: new Date().toISOString(),
          id: Date.now(),
        },
      ]);

      // Show toast notification for critical alerts
      let message;
      if (eventType === 'MOBILE_DEVICE_DETECTED') {
        message = '⚠ Mobile phone detected in frame!';
      } else {
        message =
          alert.detection_result?.message || '⚠ Security alert detected';
      }

      console.log(`💬 Toast Message: ${message}`);

      toast.error(message, {
        duration: 6000,
        style: {
          background: '#DC2626',
          color: '#fff',
          fontWeight: '600',
          fontSize: '14px',
        },
      });
    } else {
      console.log('ℹ️ Non-critical alert - not showing toast');
    }
  };

  if (!interviewData?.interviewId) {
    return null; // Will redirect
  }

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      {/* Header */}
      <Header
        userName={interviewData.userName}
        role={interviewData.role}
        persona={interviewData.persona}
        onEndInterview={handleEndInterview}
        loading={loading}
      />

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Chat Area */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-2">
            {interviewData?.messages && interviewData.messages.length > 0 ? (
              interviewData.messages.map((message, index) => (
                <ChatBubble
                  key={`message-${index}-${message.timestamp || ''}`}
                  message={{
                    ...message,
                    autoPlay:
                      message.role === 'assistant' &&
                      interviewData?.audioMode === 'voice',
                  }}
                  variant={message.role === 'user' ? 'user' : 'agent'}
                />
              ))
            ) : (
              <div className="flex items-center justify-center h-full text-gray-500">
                <p>No messages yet. Waiting for interview to start...</p>
              </div>
            )}

            {/* Thinking Indicator */}
            {loading && (
              <div className="flex justify-start mb-4">
                <div className="bg-gray-100 rounded-lg p-4 rounded-bl-none">
                  <div className="flex items-center space-x-2 text-gray-600">
                    <div className="flex space-x-1">
                      <div
                        className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
                        style={{ animationDelay: '0ms' }}
                      ></div>
                      <div
                        className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
                        style={{ animationDelay: '150ms' }}
                      ></div>
                      <div
                        className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
                        style={{ animationDelay: '300ms' }}
                      ></div>
                    </div>
                    <span className="text-sm">Agent is thinking...</span>
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Error Message */}
          {error && (
            <div className="mx-4 mb-2 p-3 bg-red-50 border border-red-200 rounded-lg">
              <p className="text-red-800 text-sm">{error}</p>
            </div>
          )}

          {/* Chat Input */}
          <ChatInput
            onSend={handleSendAnswer}
            disabled={loading}
            showVoiceInput={true}
            initialMode={interviewData?.audioMode || 'text'}
          />
        </div>

        {/* Right Panel - Webcam Only */}
        <div className="w-96 border-l border-gray-200 bg-white flex flex-col">
          {/* Webcam */}
          <div className="p-4">
            <h3 className="text-sm font-semibold text-gray-700 mb-3">
              Monitoring
            </h3>
            <WebcamFeed
              interviewId={interviewData.interviewId}
              onAlert={handleCheatingAlert}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
