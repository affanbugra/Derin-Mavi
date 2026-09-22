#pragma once
#include <map>
#include <string>
#include <string.h>
class Preferences {
 public:
  std::map<std::string,std::string> values;
  bool fail=false;
  bool begin(const char*,bool){return true;}
  bool clear(){if(fail)return false;values.clear();return true;}
  size_t putInt(const char* k,int v){return putBytes(k,&v,sizeof(v));}
  int getInt(const char* k,int d){if(!values.count(k))return d;int v;memcpy(&v,values[k].data(),sizeof(v));return v;}
  size_t putBytes(const char* k,const void* b,size_t n){if(fail)return 0;values[k]=std::string((const char*)b,n);return n;}
  size_t getBytesLength(const char* k){return values.count(k)?values[k].size():0;}
  size_t getBytes(const char* k,void* b,size_t n){if(getBytesLength(k)!=n)return 0;memcpy(b,values[k].data(),n);return n;}
};
