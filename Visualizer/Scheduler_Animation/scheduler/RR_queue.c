#include "RR_queue.h"

void insert_fun(RR_Queue* q,RR_Node* toinsert)
{
    if(q->rear == NULL)
    {
        q->start= q->rear = toinsert;
        return;
    }
    q->rear->next= toinsert;
    q->rear= toinsert;
}

RR_Node* dequeue_fun(RR_Queue* q)
{
  if(q->start=NULL){
    RR_Node* node = (RR_Node*) malloc(sizeof(RR_Node));
    node->data->AT = -1;
    return node;
  }

  RR_Node* temp = q->start;
  q->start = temp->next;
  if(q->start=NULL){
    q->rear=NULL;
  }
  return temp;
}

bool is_empty_fun(RR_Queue* q)
{
    if(q->start == NULL)
        return true;
    else
        return false;
}

RR_Queue default_rr_queue;

static void create_default_rr_q()
{
    RR_Queue q;
    default_rr_queue.start= default_rr_queue.rear = NULL;
    default_rr_queue.insert = &insert_fun;
    default_rr_queue.dequeue = &dequeue_fun;
    default_rr_queue.is_empty = &is_empty_fun;
}