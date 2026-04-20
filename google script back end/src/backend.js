var __BACKEND_V2_INSTANCE__ = null;

var iDBBackend = {
  handleRequest: function handleRequest(event, method, context) {
    return getBackendV2_().handleRequest(event, method, context);
  },
};

function getBackendV2_() {
  if (!__BACKEND_V2_INSTANCE__) {
    __BACKEND_V2_INSTANCE__ = buildBackendV2_();
  }

  return __BACKEND_V2_INSTANCE__;
}
